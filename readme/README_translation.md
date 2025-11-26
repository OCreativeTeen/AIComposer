# Ollama Translator

A Python utility for translating text and files using Ollama's local LLM (qwen2.5:7b model).

## Prerequisites

1. **Install Ollama**: Download and install Ollama from [https://ollama.ai](https://ollama.ai)
2. **Download the model**: Run `ollama pull qwen2.5:7b` to download the qwen2.5:7b model
3. **Start Ollama service**: Make sure Ollama is running locally (usually starts automatically)

## Usage

### Basic Text Translation

```python
from utility.ollama_translater import OllamaTranslater

# Initialize translator
translator = OllamaTranslater()

# Translate text
text = "Hello, how are you?"
translated = translator.translate_text(text, "Spanish")
print(translated)  # Output: "Hola, ¿cómo estás?"
```

### File Translation

```python
from utility.ollama_translater import OllamaTranslater

# Initialize translator
translator = OllamaTranslater()

# Translate a file
output_file = translator.translate_file("input.txt", "French")
print(f"Translated file saved as: {output_file}")

# Or specify custom output path
output_file = translator.translate_file("input.txt", "German", "output_german.txt")
```

### Custom Model

```python
# Use a different Ollama model
translator = OllamaTranslater(model="llama2:7b")
```

## API Reference

### `OllamaTranslater(model="qwen2.5:7b")`

Initialize the translator with a specific Ollama model.

**Parameters:**
- `model` (str): The Ollama model to use (default: "qwen2.5:7b")

### `translate_text(text, target_language)`

Translate a text string to the target language.

**Parameters:**
- `text` (str): Text to translate
- `target_language` (str): Target language (e.g., "English", "Spanish", "Chinese")

**Returns:**
- `str`: Translated text

### `translate_file(file_path, target_language, output_path=None)`

Translate the content of a file to the target language.

**Parameters:**
- `file_path` (str): Path to the input file
- `target_language` (str): Target language
- `output_path` (str, optional): Output file path. If None, creates a file with "_translated_[language]" suffix

**Returns:**
- `str`: Path to the translated file

## Error Handling

The translator includes comprehensive error handling for:
- Ollama connection issues
- File not found errors
- Empty files
- API errors

## Example Script

Run the example script to see the translator in action:

```bash
cd utility
python translation_example.py
```

## Troubleshooting

1. **Connection Error**: Make sure Ollama is running (`ollama serve`)
2. **Model Not Found**: Ensure the model is downloaded (`ollama pull qwen2.5:7b`)
3. **Port Issues**: Default port is 11434. Check if Ollama is running on a different port
4. **File Encoding**: Files are read/written with UTF-8 encoding by default 