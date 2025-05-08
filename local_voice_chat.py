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
import argparse

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Local Voice Chat with language support')
parser.add_argument('--language', '-l', type=str, default='english', 
                    help='Language for the voice chat (english, spanish, etc)')
args = parser.parse_args()

# Set language-specific variables
LANGUAGE = args.language.lower()

# Language-specific configurations
LANG_CONFIG = {
    'english': {
        'log_file': 'voice_agent.log',
        'console_prefix': '[VOICE-AI]',
        'startup_message': 'VOICE AGENT STARTING',
        'loading_models_message': 'Loading STT and TTS models...',
        'stt_success_message': 'STT model loaded successfully',
        'tts_success_message': 'TTS model loaded successfully',
        'error_loading_models': 'ERROR LOADING MODELS',
        'ollama_connection_success': 'Successfully connected to Ollama. Available models',
        'ollama_host_message': 'Using Ollama host',
        'ollama_model_message': 'Using Ollama model',
        'connection_attempt': 'Attempt',
        'connection_fail': 'Failed to connect to Ollama',
        'retry_message': 'Retrying in',
        'connection_fail_max': 'Could not connect to Ollama after',
        'continue_startup': 'Continuing startup anyway...',
        'transcribing': 'Transcribing audio...',
        'transcription_result': 'Transcribed text',
        'processing_llm': 'PROCESSING WITH LLM',
        'transcript': 'Transcript',
        'llm_usage': 'Using Ollama at',
        'llm_model': 'with model',
        'llm_response': 'LLM RESPONSE RECEIVED',
        'response_text': 'Response text',
        'generating_tts': 'Generating TTS response...',
        'first_chunk': 'First TTS chunk generated, starting audio playback',
        'tts_complete': 'TTS RESPONSE COMPLETED',
        'generated_chunks': 'Generated',
        'chunks_in': 'chunks in',
        'tts_error': 'Error during TTS generation',
        'fallback_attempt': 'Attempting to generate a simple beep as fallback...',
        'fallback_success': 'Fallback beep generated successfully',
        'fallback_fail': 'Even fallback audio generation failed',
        'echo_error': 'ERROR IN ECHO FUNCTION',
        'voice_error': 'ERROR IN VOICE PROCESSING',
        'creating_stream': 'Creating Stream object...',
        'stream_success': 'Stream created successfully',
        'stream_error': 'Error creating Stream',
        'launching_ui': 'Launching Voice Agent UI...',
        'ui_title': 'Voice Assistant',
        'ui_error': 'Error launching UI',
        'voice_recording': 'VOICE RECORDING RECEIVED',
        'timestamp': 'Timestamp',
        'no_chunks': 'No TTS chunks produced after',
        'tts_timeout': 'TTS generation did not complete within',
        'truncated': 'message may be truncated',
        'full_message': 'processed full message',
        'seconds': 'seconds',
        'system_prompt': 'You are a helpful assistant in a voice conversation. Keep your responses concise and suitable for text-to-speech.',
    },
    'spanish': {
        'log_file': 'voice_agent_spanish.log',
        'console_prefix': '[VOZ-IA]',
        'startup_message': 'AGENTE DE VOZ INICIANDO',
        'loading_models_message': 'Cargando modelos STT y TTS...',
        'stt_success_message': 'Modelo STT cargado correctamente',
        'tts_success_message': 'Modelo TTS cargado correctamente',
        'error_loading_models': 'ERROR AL CARGAR LOS MODELOS',
        'ollama_connection_success': 'Conectado exitosamente a Ollama. Modelos disponibles',
        'ollama_host_message': 'Usando host de Ollama',
        'ollama_model_message': 'Usando modelo de Ollama',
        'connection_attempt': 'Intento',
        'connection_fail': 'Error al conectar con Ollama',
        'retry_message': 'Reintentando en',
        'connection_fail_max': 'No se pudo conectar a Ollama después de',
        'continue_startup': 'Continuando con el inicio de todos modos...',
        'transcribing': 'Transcribiendo audio...',
        'transcription_result': 'Texto transcrito',
        'processing_llm': 'PROCESANDO CON LLM',
        'transcript': 'Transcripción',
        'llm_usage': 'Usando Ollama en',
        'llm_model': 'con modelo',
        'llm_response': 'RESPUESTA DEL LLM RECIBIDA',
        'response_text': 'Texto de respuesta',
        'generating_tts': 'Generando respuesta TTS...',
        'first_chunk': 'Primer fragmento de TTS generado, comenzando la reproducción de audio',
        'tts_complete': 'RESPUESTA TTS COMPLETADA',
        'generated_chunks': 'Generados',
        'chunks_in': 'fragmentos en',
        'tts_error': 'Error durante la generación de TTS',
        'fallback_attempt': 'Intentando generar un pitido simple como respaldo...',
        'fallback_success': 'Pitido de respaldo generado con éxito',
        'fallback_fail': 'Incluso la generación de audio de respaldo falló',
        'echo_error': 'ERROR EN LA FUNCIÓN ECHO',
        'voice_error': 'ERROR EN EL PROCESAMIENTO DE VOZ',
        'creating_stream': 'Creando objeto Stream...',
        'stream_success': 'Stream creado exitosamente',
        'stream_error': 'Error al crear Stream',
        'launching_ui': 'Lanzando la interfaz del Agente de Voz...',
        'ui_title': 'Asistente de Voz en Español',
        'ui_error': 'Error al lanzar la interfaz',
        'voice_recording': 'GRABACIÓN DE VOZ RECIBIDA',
        'timestamp': 'Marca de tiempo',
        'no_chunks': 'No se produjeron fragmentos de TTS después de',
        'tts_timeout': 'La generación de TTS no se completó en',
        'truncated': 'el mensaje puede estar truncado',
        'full_message': 'mensaje procesado completamente',
        'seconds': 'segundos',
        'system_prompt': 'Eres un asistente útil en una conversación por voz. Mantén tus respuestas concisas y adecuadas para texto-a-voz. Responde siempre en español. Eres amable y servicial.',
    }
}

# Default to English if specified language is not supported
if LANGUAGE not in LANG_CONFIG:
    logger.warning(f"Language '{LANGUAGE}' not supported, defaulting to English")
    LANGUAGE = 'english'

# Get language configuration
lang = LANG_CONFIG[LANGUAGE]

# Configure file logging first to capture everything
log_file = lang['log_file']
logger.remove()  # Remove default handlers
logger.add(log_file, rotation="10 MB", level="DEBUG", 
           format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}")

# Configure Ollama host from environment variable if available
# In Docker, this will be set to host.docker.internal:11434
ollama_host = os.environ.get("OLLAMA_HOST", "localhost:11434")
os.environ["OLLAMA_HOST"] = ollama_host
logger.info(f"{lang['ollama_host_message']}: {ollama_host}")

# Get model from environment variable (set by start.sh), default to granite3-dense:latest
ollama_model = os.environ.get("OLLAMA_MODEL", "granite3-dense:latest")
logger.info(f"{lang['ollama_model_message']}: {ollama_model}")

# Add our custom-formatted console logger with more visible formatting
logger.add(
    sys.stdout,
    format=f"<yellow>{lang['console_prefix']}</yellow> <green>{{time:HH:mm:ss}}</green> | <level>{{level: <8}}</level> | {{message}}",
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
        f.write(f"\n{message}{lang['timestamp']}: {timestamp}\n\n")

# Print very visible startup message to both console and file
log_event(lang['startup_message'], f"Version 1.0.0 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Very visible debug message for script progress
logger.info(lang['loading_models_message'])

# Test connection to Ollama
logger.info(f"{lang['llm_usage']} {ollama_host}...")
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
        
        logger.info(f"✅ {lang['ollama_connection_success']}: {model_names}")
        connected = True
        break
    except Exception as e:
        logger.warning(f"❌ {lang['connection_attempt']} {i+1}/{max_retries} - {lang['connection_fail']}: {e}")
        if i < max_retries - 1:
            logger.info(f"{lang['retry_message']} {retry_delay} {lang['seconds']}...")
            time.sleep(retry_delay)

if not connected:
    logger.error(f"❌ {lang['connection_fail_max']} {max_retries} {lang['connection_attempt']}. {lang['continue_startup']}")
    logger.info(f"{lang['continue_startup']}")

try:
    # Try to load language-specific model if available
    if LANGUAGE != 'english':
        try:
            # Map languages to proper locale codes
            lang_code_map = {
                'english': 'en-us',
                'spanish': 'es-es'
            }
            
            # Get the proper language code with fallback to first 2 chars if not in map
            lang_code = lang_code_map.get(LANGUAGE, LANGUAGE[:2])
            
            # Attempt to load language-specific STT model if available
            # Remove unsupported 'language' parameter
            stt_model = get_stt_model()
            logger.info(f"✅ {lang['stt_success_message']} ({LANGUAGE}, code: {lang_code})")
        except Exception as lang_error:
            logger.warning(f"Could not load {LANGUAGE}-specific STT model: {lang_error}")
            logger.info("Falling back to default STT model...")
            # Fall back to default model
            stt_model = get_stt_model(lang_code=lang_code)
            logger.info(f"✅ {lang['stt_success_message']} (default)")
        
        try:
            # Attempt to load language-specific TTS model if available
            # Remove unsupported 'language' parameter if it causes issues
            tts_model = get_tts_model(language=lang_code)
            logger.info(f"✅ {lang['tts_success_message']} ({LANGUAGE}, code: {lang_code})")
        except Exception as lang_error:
            logger.warning(f"Could not load {LANGUAGE}-specific TTS model: {lang_error}")
            logger.info("Falling back to default TTS model...")
            # Fall back to default model
            tts_model = get_tts_model()
            logger.info(f"✅ {lang['tts_success_message']} (default)")
    else:
        # Load default English models
        stt_model = get_stt_model()  # moonshine/base
        logger.info(f"✅ {lang['stt_success_message']}")
        
        tts_model = get_tts_model()  # kokoro
        logger.info(f"✅ {lang['tts_success_message']}")
except Exception as e:
    logger.exception(f"❌ {lang['error_loading_models']}: {e}")
    with open(log_file, "a") as f:
        f.write(f"{lang['error_loading_models']}: {e}\n")

# Function to generate TTS with timeout
def generate_tts_with_timeout(text, timeout=120):  # 120 seconds timeout
    """Generate TTS with a timeout to prevent hanging"""
    chunks = []
    chunk_event = threading.Event()
    tts_error = None
    chunks_yielded = 0
    generation_complete = False
    
    def tts_worker():
        nonlocal chunks, tts_error, generation_complete
        try:
            # Collect chunks from the generator
            for chunk in tts_model.stream_tts_sync(text):
                chunks.append(chunk)
                chunk_event.set()  # Signal that we got at least one chunk
            generation_complete = True
        except Exception as e:
            tts_error = e
            chunk_event.set()  # Signal even if there's an error
    
    # Start TTS generation in a separate thread
    thread = threading.Thread(target=tts_worker)
    thread.daemon = True
    thread.start()
    
    # Wait for the first chunk with timeout
    start_time = time.time()
    first_chunk_timeout = min(timeout, 15)  # Wait up to 15 seconds for first chunk
    
    if not chunk_event.wait(first_chunk_timeout):
        logger.warning(f"⚠️ {lang['no_chunks']} {first_chunk_timeout} {lang['seconds']}")
    
    # If we got an error, raise it
    if tts_error:
        raise tts_error
    
    # Continue yielding chunks as they become available
    end_time = start_time + timeout
    
    while time.time() < end_time:
        # Yield any new chunks that are available
        while chunks_yielded < len(chunks):
            yield chunks[chunks_yielded]
            chunks_yielded += 1
            
        # If thread is done and all chunks yielded, we're done
        if generation_complete and chunks_yielded >= len(chunks):
            logger.info(f"✅ {lang['full_message']}")
            break
            
        # Small sleep to prevent CPU spinning
        time.sleep(0.05)
    
    # Final check for any remaining chunks
    while chunks_yielded < len(chunks):
        yield chunks[chunks_yielded]
        chunks_yielded += 1
        
    # Log warning if timed out
    if not generation_complete:
        logger.warning(f"⚠️ {lang['tts_timeout']} {timeout} {lang['seconds']} - {lang['truncated']}")

# Define the echo function with heavy debugging and timeout
def echo(audio):
    try:
        # Log the voice recording event with timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event(f"🎤 {lang['voice_recording']}", f"{lang['timestamp']}: {timestamp}")
        
        # Process the audio
        logger.info(lang['transcribing'])
        transcript = stt_model.stt(audio)
        logger.info(f"🎤 {lang['transcription_result']}: \"{transcript}\"")
        
        # Log LLM request
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event(f"🔄 {lang['processing_llm']}", f"{lang['transcript']}: \"{transcript}\"")
        
        # Get LLM response using the model from environment variable
        logger.info(f"{lang['llm_usage']} {ollama_host} {lang['llm_model']} {ollama_model}")
        response = chat(
            model=ollama_model, 
            messages=[
                {
                    "role": "system",
                    "content": lang['system_prompt']
                },
                {"role": "user", "content": transcript}
            ],
            options={"num_predict": 200}  # Limit response length
        )
        response_text = response["message"]["content"]
        
        # Log LLM response
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event(f"🤖 {lang['llm_response']}", f"{lang['timestamp']}: {timestamp}")
        logger.info(f"{lang['response_text']}: \"{response_text[:100]}{'...' if len(response_text) > 100 else ''}\"")
        
        # Return audio chunks with timeout protection
        logger.info(lang['generating_tts'])
        tts_start_time = time.time()
        chunk_count = 0
        
        try:
            # Use our timeboxed TTS generation function
            for audio_chunk in generate_tts_with_timeout(response_text, timeout=30):
                chunk_count += 1
                if chunk_count == 1:
                    logger.info(f"🔊 {lang['first_chunk']}")
                elif chunk_count % 5 == 0:  # Log every 5 chunks to avoid excessive logging
                    logger.debug(f"Generated TTS chunk #{chunk_count}")
                yield audio_chunk
            
            tts_time = time.time() - tts_start_time
            log_event(f"✅ {lang['tts_complete']}", f"{lang['generated_chunks']} {chunk_count} {lang['chunks_in']} {tts_time:.2f}s")
        except Exception as tts_err:
            logger.exception(f"❌ {lang['tts_error']}: {tts_err}")
            # Try a fallback response if TTS fails
            try:
                logger.info(lang['fallback_attempt'])
                # Generate a simple beep sound as fallback
                import numpy as np
                sample_rate = 16000  # Standard sample rate
                duration = 0.5  # half second beep
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                beep = np.sin(2 * np.pi * 440 * t) * 0.5  # 440 Hz tone at half volume
                beep = (beep * 32767).astype(np.int16).tobytes()
                yield beep
                logger.info(lang['fallback_success'])
            except Exception as fallback_err:
                logger.exception(f"❌ {lang['fallback_fail']}: {fallback_err}")
        
    except Exception as e:
        error_msg = f"❌ {lang['echo_error']}: {e}"
        logger.exception(error_msg)
        log_event(f"❌ {lang['voice_error']}", str(e))


logger.info(lang['creating_stream'])

try:
    # Initialize the stream
    stream = Stream(ReplyOnPause(echo), modality="audio", mode="send-receive")
    logger.info(f"✅ {lang['stream_success']}")
except Exception as e:
    logger.exception(f"❌ {lang['stream_error']}: {e}")
    
# Launch the UI
logger.info(f"🚀 {lang['launching_ui']}")
try:
    # Configure UI with language and model info
    ui_title = f"{lang['ui_title']} (Model: {ollama_model})"
    stream.ui.title = ui_title
    stream.ui.launch()
except Exception as e:
    logger.exception(f"❌ {lang['ui_error']}: {e}")