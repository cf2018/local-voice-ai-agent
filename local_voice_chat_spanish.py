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
log_file = "voice_agent_spanish.log"
logger.remove()  # Remove default handlers
logger.add(log_file, rotation="10 MB", level="DEBUG", 
           format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}")

# Configure Ollama host from environment variable if available
# In Docker, this will be set to host.docker.internal:11434
ollama_host = os.environ.get("OLLAMA_HOST", "localhost:11434")
os.environ["OLLAMA_HOST"] = ollama_host
logger.info(f"Usando host de Ollama: {ollama_host}")

# Get model from environment variable (set by start.sh), default to gemma3:1b
ollama_model = os.environ.get("OLLAMA_MODEL", "gemma3:1b")
logger.info(f"Usando modelo de Ollama: {ollama_model}")

# Add our custom-formatted console logger with more visible formatting
logger.add(
    sys.stdout,
    format="<yellow>[VOZ-IA]</yellow> <green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
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
log_event("AGENTE DE VOZ INICIANDO", f"Versión 1.0.0 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Very visible debug message for script progress
logger.info("Cargando modelos STT y TTS...")

# Try to load Spanish model if available through language parameter
# Note: This is a hypothetical implementation - check FastRTC documentation for actual language support
try:
    # Try to load a Spanish language model if available
    # First attempt with explicit language parameter
    try:
        # Attempt to load Spanish STT model - may need adjustment based on actual FastRTC API
        stt_model = get_stt_model(language="es")
        logger.info("✅ Modelo STT en español cargado correctamente")
    except Exception as lang_error:
        logger.warning(f"No se pudo cargar el modelo STT específico para español: {lang_error}")
        logger.info("Cargando modelo STT predeterminado...")
        # Fall back to default model
        stt_model = get_stt_model()
        logger.info("✅ Modelo STT predeterminado cargado")
    
    # Try to load Spanish TTS model if available
    try:
        # Attempt to load Spanish TTS model - may need adjustment based on actual FastRTC API
        tts_model = get_tts_model(language="es")
        logger.info("✅ Modelo TTS en español cargado correctamente")
    except Exception as lang_error:
        logger.warning(f"No se pudo cargar el modelo TTS específico para español: {lang_error}")
        logger.info("Cargando modelo TTS predeterminado...")
        # Fall back to default model
        tts_model = get_tts_model()
        logger.info("✅ Modelo TTS predeterminado cargado")
    
except Exception as e:
    logger.exception(f"❌ Error al cargar los modelos: {e}")
    with open(log_file, "a") as f:
        f.write(f"ERROR AL CARGAR LOS MODELOS: {e}\n")

# Test connection to Ollama
logger.info(f"Probando conexión a Ollama en {ollama_host}...")
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
        
        logger.info(f"✅ Conectado exitosamente a Ollama. Modelos disponibles: {model_names}")
        connected = True
        break
    except Exception as e:
        logger.warning(f"❌ Intento {i+1}/{max_retries} - Error al conectar con Ollama: {e}")
        if i < max_retries - 1:
            logger.info(f"Reintentando en {retry_delay} segundos...")
            time.sleep(retry_delay)

if not connected:
    logger.error(f"❌ No se pudo conectar a Ollama después de {max_retries} intentos. Asegúrese de que Ollama está ejecutándose en {ollama_host}")
    logger.info("Continuando con el inicio de todos modos...")

# Function to generate TTS with timeout
def generate_tts_with_timeout(text, timeout=60):
    """Generate TTS with a timeout to prevent hanging"""
    chunks = []
    chunk_event = threading.Event()
    tts_error = None
    chunks_yielded = 0
    
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
        logger.warning(f"⚠️ No se produjeron fragmentos de TTS después de {first_chunk_timeout} segundos")
    
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
        if not thread.is_alive() and chunks_yielded >= len(chunks):
            break
            
        # Small sleep to prevent CPU spinning
        time.sleep(0.05)
    
    # Final check for any remaining chunks
    while chunks_yielded < len(chunks):
        yield chunks[chunks_yielded]
        chunks_yielded += 1
        
    # Log a warning if timed out
    if thread.is_alive():
        logger.warning(f"⚠️ La generación de TTS no se completó en {timeout} segundos")
        thread.join(0.1)  # Try to clean up thread

# Define the echo function with heavy debugging and timeout
def echo(audio):
    try:
        # Log the voice recording event with timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event("🎤 GRABACIÓN DE VOZ RECIBIDA", f"Marca de tiempo: {timestamp}")
        
        # Process the audio
        logger.info("Transcribiendo audio...")
        transcript = stt_model.stt(audio)
        logger.info(f"🎤 Texto transcrito: \"{transcript}\"")
        
        # Log LLM request
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event("🔄 PROCESANDO CON LLM", f"Transcripción: \"{transcript}\"")
        
        # Get LLM response in Spanish using the model from environment variable
        logger.info(f"Usando Ollama en {ollama_host} con modelo {ollama_model}")
        response = chat(
            model=ollama_model, 
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente útil en una conversación por voz. Mantén tus respuestas concisas y adecuadas para texto-a-voz. Responde siempre en español. Eres amable y servicial."
                },
                {"role": "user", "content": transcript}
            ],
            options={"num_predict": 200}  # Limit response length
        )
        response_text = response["message"]["content"]
        
        # Log LLM response
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_event("🤖 RESPUESTA DEL LLM RECIBIDA", f"Marca de tiempo: {timestamp}")
        logger.info(f"Texto de respuesta: \"{response_text[:100]}{'...' if len(response_text) > 100 else ''}\"")
        
        # Return audio chunks with timeout protection
        logger.info("Generando respuesta TTS...")
        tts_start_time = time.time()
        chunk_count = 0
        
        try:
            # Use our timeboxed TTS generation function
            for audio_chunk in generate_tts_with_timeout(response_text, timeout=30):
                chunk_count += 1
                if chunk_count == 1:
                    logger.info("🔊 Primer fragmento de TTS generado, comenzando la reproducción de audio")
                elif chunk_count % 5 == 0:  # Log every 5 chunks to avoid excessive logging
                    logger.debug(f"Fragmento de TTS #{chunk_count} generado")
                yield audio_chunk
            
            tts_time = time.time() - tts_start_time
            log_event("✅ RESPUESTA TTS COMPLETADA", f"Generados {chunk_count} fragmentos en {tts_time:.2f}s")
        except Exception as tts_err:
            logger.exception(f"❌ Error durante la generación de TTS: {tts_err}")
            # Try a fallback response if TTS fails
            try:
                logger.info("Intentando generar un pitido simple como respaldo...")
                # Generate a simple beep sound as fallback
                import numpy as np
                sample_rate = 16000  # Standard sample rate
                duration = 0.5  # half second beep
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                beep = np.sin(2 * np.pi * 440 * t) * 0.5  # 440 Hz tone at half volume
                beep = (beep * 32767).astype(np.int16).tobytes()
                yield beep
                logger.info("Pitido de respaldo generado con éxito")
            except Exception as fallback_err:
                logger.exception(f"❌ Incluso la generación de audio de respaldo falló: {fallback_err}")
        
    except Exception as e:
        error_msg = f"❌ ERROR EN LA FUNCIÓN ECHO: {e}"
        logger.exception(error_msg)
        log_event("❌ ERROR EN EL PROCESAMIENTO DE VOZ", str(e))


logger.info("Creando objeto Stream...")

try:
    # Initialize the stream
    stream = Stream(ReplyOnPause(echo), modality="audio", mode="send-receive")
    logger.info("✅ Stream creado exitosamente")
except Exception as e:
    logger.exception(f"❌ Error al crear Stream: {e}")
    
# Launch the UI
logger.info("🚀 Lanzando la interfaz del Agente de Voz...")
try:
    # Configure UI with Spanish title and model info
    stream.ui.title = f"Asistente de Voz en Español (Modelo: {ollama_model})"
    stream.ui.launch()  # Launch with Spanish title and model info
except Exception as e:
    logger.exception(f"❌ Error al lanzar la interfaz: {e}")