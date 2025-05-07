#!/bin/bash
set -e

# Configure logging
LOGFILE="/app/logs/startup.log"
mkdir -p /app/logs

echo "===============================================" >> $LOGFILE
echo "Starting container setup at $(date)" >> $LOGFILE
echo "===============================================" >> $LOGFILE

# Parse command-line arguments
LANGUAGE="english"
MODEL="granite3-dense:latest"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --language|-l)
      LANGUAGE="$2"
      shift 2
      ;;
    --english|-en)
      LANGUAGE="english"
      shift
      ;;
    --model|-m)
      MODEL="$2"
      shift 2
      ;;
    --advanced|-a)
      ADVANCED=true
      shift
      ;;
    *)
      # Unknown option
      echo "Unknown option: $1"
      echo "Usage: $0 [--language|-l english] [--english|-en] [--model|-m MODEL_NAME] [--advanced|-a]"
      exit 1
      ;;
  esac
done

# Log the selected language and model
echo "Setting language to $LANGUAGE" >> $LOGFILE
echo "Setting model to $MODEL" >> $LOGFILE

# Function to log messages
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOGFILE
}

log "Starting Ollama setup..."
log "Selected model: $MODEL"

# Download and install Ollama if not already installed
if [ ! -f "/usr/local/bin/ollama" ]; then
  log "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
  
  log "Ollama installed successfully"
else
  log "Ollama already installed"
fi

# Start Ollama server in the background
log "Starting Ollama server..."

ollama serve &
OLLAMA_PID=$!

log "Ollama started with PID: $OLLAMA_PID"

# Wait for Ollama server to become available
log "Waiting for Ollama server to start..."

timeout=30
counter=0
until curl -s http://localhost:11434/api/tags >/dev/null 2>&1 || [ $counter -eq $timeout ]; do
  counter=$((counter+1))
  
  log "Waiting for Ollama server... ($counter/$timeout)"
  
  sleep 1
done

if [ $counter -eq $timeout ]; then
  log "ERROR: Timed out waiting for Ollama server to start"
  exit 1
fi

log "Ollama server is up and running"

# Pull the selected model and gemma3:4b if using advanced mode
log "Pulling $MODEL model (this may take a while)..."

ollama pull $MODEL

# Also pull gemma3:4b if advanced mode is selected
if [ "$ADVANCED" = true ]; then
  log "Pulling gemma3:4b model for advanced mode..."
  ollama pull gemma3:4b
fi

# Verify the model was pulled successfully
counter=0
timeout=10
model_available=false

while [ $counter -lt $timeout ]; do
  if ollama list | grep -q "$MODEL"; then
    log "✅ $MODEL model pulled successfully"
    model_available=true
    break
  fi
  
  log "Waiting for $MODEL model to be fully loaded... ($counter/$timeout)"
  
  counter=$((counter+1))
  sleep 2
done

if [ "$model_available" = false ]; then
  log "⚠️ Warning: Couldn't verify $MODEL model availability, but will continue anyway"
fi

# Verify 4b model is available if advanced mode is selected
if [ "$ADVANCED" = true ]; then
  counter=0
  timeout=10
  model_available=false

  while [ $counter -lt $timeout ]; do
    if ollama list | grep -q "gemma3:4b"; then
      log "✅ gemma3:4b model pulled successfully"
      model_available=true
      break
    fi
    
    log "Waiting for gemma3:4b model to be fully loaded... ($counter/$timeout)"
    
    counter=$((counter+1))
    sleep 2
  done

  if [ "$model_available" = false ]; then
    log "⚠️ Warning: Couldn't verify gemma3:4b model availability, but will continue anyway"
  fi
fi

# Set environment variables
export OLLAMA_HOST=localhost:11434
export OLLAMA_MODEL=$MODEL

log "Set OLLAMA_HOST to $OLLAMA_HOST"
log "Set OLLAMA_MODEL to $MODEL"

# Create a named pipe for log streaming
PIPE_PATH="/tmp/voice_agent_pipe"
mkfifo $PIPE_PATH

log "Created named pipe for log streaming at $PIPE_PATH"

# Start log streaming in the background
( cat $PIPE_PATH | tee -a /app/logs/voice_agent.log & )

log "Started log streaming process"

# Start the voice assistant with output redirected to both console and log file
log "Starting voice assistant application..."
# Choose between basic or advanced version
if [ "$ADVANCED" = true ]; then
  python -u /app/local_voice_chat_advanced.py 2>&1 | tee -a /app/voice_agent.log $PIPE_PATH
else
  python -u /app/local_voice_chat.py 2>&1 | tee -a /app/voice_agent.log $PIPE_PATH
fi

# Clean up if the Python script exits
log "Voice assistant exited, shutting down Ollama..."

if [ -n "$OLLAMA_PID" ]; then
  kill $OLLAMA_PID || log "Failed to kill Ollama process"
fi

# Clean up the named pipe
rm -f $PIPE_PATH

log "Removed named pipe"
log "Container shutdown complete"