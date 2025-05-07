from fastrtc import ReplyOnPause, Stream, get_stt_model, get_tts_model
from ollama import chat
import os
import sys
import datetime
import logging
from loguru import logger
import io
import time
import threading
import signal
import concurrent.futures

# Configure file logging first to capture everything
log_file = "voice_agent.log"
logger.remove()  # Remove default handlers
logger.add(log_file, rotation="10 MB", level="DEBUG", 
           format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}")

# Configure Ollama host from environment variable if available
# In Docker, this will be set to host.docker.internal:11434
ollama_host = os.environ.get("OLLAMA_HOST", "localhost:11434")
os.environ["OLLAMA_HOST"] = ollama_host
logger.info(f"Using Ollama host: {ollama_host}")

# Get model from environment variable (set by start.sh), default to gemma3:1b
ollama_model = os.environ.get("OLLAMA_MODEL", "gemma3:1b")
logger.info(f"Using Ollama model: {ollama_model}")

# Add our custom-formatted console logger with more visible formatting
logger.add(
    sys.stdout,
    format="<yellow>[VOICE-AI]</yellow> <green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
    filter=lambda record: "candidate" not in record["message"].lower()
)

# Function to print highly visible event markers
def log_event(event_name, details=None):
    """Print a highly visible event marker to both console and file"""
    border = "#" * 80
    message = f"\n{border}\n{event_name:^80}\n"
    if details:
        message += f"{details:^80}\n"
    message += f"{border}\n"
    
    logger.info(message)
    # Also write raw to file to ensure visibility
    with open(log_file, "a") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        f.write(f"\n{message}Timestamp: {timestamp}\n\n")

# Print very visible startup message to both console and file
log_event("VOICE AGENT STARTING", f"Version 1.0.0 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Very visible debug message for script progress
logger.info("Loading STT and TTS models...")

# Test connection to Ollama
logger.info(f"Testing connection to Ollama at {ollama_host}...")
max_retries = 5
retry_delay = 2
connected = False

for i in range(max_retries):
    try:
        # Simple test to check if Ollama is accessible
        from ollama import Client
        client = Client(host=ollama_host)
        models = client.list()
        
        # More robust handling of the models response
        model_names = []
        if isinstance(models, dict) and 'models' in models:
            for model in models.get('models', []):
                if isinstance(model, dict) and 'name' in model:
                    model_names.append(model['name'])
        
        logger.info(f"✅ Successfully connected to Ollama. Available models: {model_names}")
        connected = True
        break
    except Exception as e:
        logger.warning(f"❌ Attempt {i+1}/{max_retries} - Failed to connect to Ollama: {e}")
        if i < max_retries - 1:
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

if not connected:
    logger.error(f"❌ Could not connect to Ollama after {max_retries} attempts. Please ensure Ollama is running at {ollama_host}")
    logger.info("Continuing startup anyway...")

try:
    # Load models
    stt_model = get_stt_model()  # moonshine/base
    logger.info("✅ STT model loaded successfully")
    
    tts_model = get_tts_model()  # kokoro
    logger.info("✅ TTS model loaded successfully")
except Exception as e:
    logger.exception(f"❌ Error loading models: {e}")
    with open(log_file, "a") as f:
        f.write(f"ERROR LOADING MODELS: {e}\n")

# Function to generate TTS with timeout
def generate_tts_with_timeout(text, timeout=60):
    """Generate TTS with a timeout to prevent hanging"""
    chunks = []
    chunk_event = threading.Event()
    tts_error = None
    
    def tts_worker():
        nonlocal chunks, tts_error
        try:
            # Collect chunks from the generator
            for chunk in tts_model.stream_tts_sync(text):
                chunks.append(chunk)
                chunk_event.set()  # Signal that we got at least one chunk
        except Exception as e:
            tts_error = e
            chunk_event.set()  # Signal even if there's an error
    
    # Start TTS generation in a separate thread
    thread = threading.Thread(target=tts_worker)
    thread.daemon = True
    thread.start()
    
    # Wait for the first chunk with timeout
    start_time = time.time()
    first_chunk_timeout = min(timeout, 10)  # Wait up to 10 seconds for first chunk
    
    if not chunk_event.wait(first_chunk_timeout):
        logger.warning(f"⚠️ No TTS chunks produced after {first_chunk_timeout} seconds")
    
    # If we got an error, raise it
    if tts_error:
        raise tts_error
        
    # Return chunks and continue in background
    for chunk in chunks:
        yield chunk
    
    remaining_time = max(0, timeout - (time.time() - start_time))
    thread.join(remaining_time)  # Give the thread some time to finish
    
    # After timeout, just return any remaining chunks that were generated
    if thread.is_alive():
        logger.warning(f"⚠️ TTS generation did not complete within {timeout} seconds")
    else:
        for chunk in chunks[len(chunks):]:  # Get any new chunks that weren't yielded yet
            yield chunk

# Define the echo function with heavy debugging and timeout
def echo(audio):
    try:
        # Log the voice recording event with timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event("🎤 VOICE RECORDING RECEIVED", f"Timestamp: {timestamp}")
        
        # Process the audio
        logger.info("Transcribing audio...")
        transcript = stt_model.stt(audio)
        logger.info(f"🎤 Transcribed text: \"{transcript}\"")
        
        # Log LLM request
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event("🔄 PROCESSING WITH LLM", f"Transcript: \"{transcript}\"")
        
        # Get LLM response using the model from environment variable
        logger.info(f"Using Ollama at {ollama_host} with model {ollama_model}")
        response = chat(
            model=ollama_model, 
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant in a voice conversation. Keep your responses concise and suitable for text-to-speech."
                },
                {"role": "user", "content": transcript}
            ],
            options={"num_predict": 200}  # Limit response length
        )
        response_text = response["message"]["content"]
        
        # Log LLM response
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event("🤖 LLM RESPONSE RECEIVED", f"Timestamp: {timestamp}")
        logger.info(f"Response text: \"{response_text[:100]}{'...' if len(response_text) > 100 else ''}\"")
        
        # Return audio chunks with timeout protection
        logger.info("Generating TTS response...")
        tts_start_time = time.time()
        chunk_count = 0
        
        try:
            # Use our timeboxed TTS generation function
            for audio_chunk in generate_tts_with_timeout(response_text, timeout=30):
                chunk_count += 1
                if chunk_count == 1:
                    logger.info("🔊 First TTS chunk generated, starting audio playback")
                elif chunk_count % 5 == 0:  # Log every 5 chunks to avoid excessive logging
                    logger.debug(f"Generated TTS chunk #{chunk_count}")
                yield audio_chunk
            
            tts_time = time.time() - tts_start_time
            log_event("✅ TTS RESPONSE COMPLETED", f"Generated {chunk_count} chunks in {tts_time:.2f}s")
        except Exception as tts_err:
            logger.exception(f"❌ Error during TTS generation: {tts_err}")
            # Try a fallback response if TTS fails
            try:
                logger.info("Attempting to generate a simple beep as fallback...")
                # Generate a simple beep sound as fallback
                import numpy as np
                sample_rate = 16000  # Standard sample rate
                duration = 0.5  # half second beep
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                beep = np.sin(2 * np.pi * 440 * t) * 0.5  # 440 Hz tone at half volume
                beep = (beep * 32767).astype(np.int16).tobytes()
                yield beep
                logger.info("Fallback beep generated successfully")
            except Exception as fallback_err:
                logger.exception(f"❌ Even fallback audio generation failed: {fallback_err}")
        
    except Exception as e:
        error_msg = f"❌ ERROR IN ECHO FUNCTION: {e}"
        logger.exception(error_msg)
        log_event("❌ ERROR IN VOICE PROCESSING", str(e))


logger.info("Creating Stream object...")

try:
    # Initialize the stream
    stream = Stream(ReplyOnPause(echo), modality="audio", mode="send-receive")
    logger.info("✅ Stream created successfully")
except Exception as e:
    logger.exception(f"❌ Error creating Stream: {e}")
    
# Launch the UI
logger.info("🚀 Launching Voice Agent UI...")
try:
    # Configure UI with model info
    stream.ui.title = f"Voice Assistant (Model: {ollama_model})"
    stream.ui.launch()
except Exception as e:
    logger.exception(f"❌ Error launching UI: {e}")