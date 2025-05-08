# Local Voice AI Agent

A real-time voice chat application powered by local AI models. This project allows you to have voice conversations with AI models like Granite running locally on your machine.

## Features

- Real-time speech-to-text conversion
- Local LLM inference using Ollama
- Text-to-speech response generation
- Web interface for interaction
- Phone number interface option
- Multiple language support (English, Spanish)
- Configurable AI model (granite3-dense:latest default)

## Note on Ollama
- Ollama runs within the container itself, is all contained
- If you have it already running on linux, stop it with systemctl stop ollama, otherwise a port conflict will arise

## Prerequisites

- Docker and Docker Compose
- Microphone access for voice input

## Installation

### Using Docker (Recommended)

1. Clone the repository

```bash
git clone https://github.com/cf2018/local-voice-ai-agent.git
cd local-voice-ai-agent
```

2. Build and run with Docker Compose

```bash
docker compose up
```

This will:
- Build the Docker image with all required dependencies
- Start Ollama service inside the container
- Download the default AI model (granite3-dense:latest)
- Run the voice agent application with default settings (English language)

## Usage

### Starting with Default Settings

Simply run:

```bash
docker compose up
```

### Using Different Languages

You can specify a different language:

```bash
docker compose run --rm -e LANGUAGE=spanish voice-agent
```

### Using Different Models

You can use different Ollama models by modifying the environment variables:

```yaml
services:
  voice-agent:
    # ...other settings...
    environment:
      # ...other environment variables...
      - MODEL=llama3:8b  # Change to your preferred model
```

Or use command-line override:

```bash
docker compose run --rm -e MODEL=llama3:8b voice-agent
```

### Combining Options

You can combine different options:

```bash
# Spanish language with custom model
docker compose run --rm -e LANGUAGE=spanish -e MODEL=llama3:8b voice-agent
```

## Model Examples

The application works with various Ollama models. Here are some examples:

| Model | Size | Description | Example Command |
|-------|------|-------------|----------------|
| granite3-dense:latest | - | Default model | `docker compose run --rm -e MODEL=granite3-dense:latest voice-agent` |
| gemma3:1b | 1B | Lightweight model | `docker compose run --rm -e MODEL=gemma3:1b voice-agent` |
| gemma3:4b | 4B | Better quality responses | `docker compose run --rm -e MODEL=gemma3:4b voice-agent` |
| llama3:8b | 8B | More capable general model | `docker compose run --rm -e MODEL=llama3:8b voice-agent` |
| mistral:7b | 7B | Good all-around performer | `docker compose run --rm -e MODEL=mistral:7b voice-agent` |
| qwen2:7b | 7B | Multilingual capabilities | `docker compose run --rm -e MODEL=qwen2:7b voice-agent` |

### Phone Number Interface
Get a temporary phone number that anyone can call to interact with your AI:

```bash
docker compose run --rm -e PHONE=true voice-agent
```

This will provide you with a temporary phone number that you can call to interact with the AI using your voice.

## Persistent Models

The Docker setup uses a named volume (`ollama-data`) to persist downloaded models between container restarts. This means you only need to download models once.

## Logs

Logs are stored in the `logs` directory, which is mounted as a volume in the Docker container. You can view them at:

- General application log: `logs/voice_agent.log`
- Spanish language log: `logs/voice_agent_spanish.log`
- Startup log: `logs/startup.log`

## How it works

The application uses:
- `FastRTC` for WebRTC communication
- `Moonshine` for local speech-to-text conversion
- `Kokoro` for text-to-speech synthesis
- `Ollama` for running local LLM inference with various models

When you speak, your audio is:
1. Transcribed to text using Moonshine
2. Sent to a local LLM via Ollama for processing
3. The LLM response is converted back to speech with Kokoro
4. The audio response is streamed back to you via FastRTC
