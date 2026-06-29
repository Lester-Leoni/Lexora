import bootstrap  # CRITICAL: Must be the absolute first line
import os
import sys
import json
import traceback

def sanitize_text(text):
    if not isinstance(text, str):
        return text
    return text.encode('utf-8', errors='replace').decode('utf-8')

def send_json_to_parent(data):
    try:
        if isinstance(data, dict) and "payload" in data and isinstance(data["payload"], str):
            data["payload"] = sanitize_text(data["payload"])
            
        json_str = json.dumps(data, ensure_ascii=False)
        json_bytes = json_str.encode('utf-8', errors='replace')
        
        sys.stdout.buffer.write(json_bytes + b'\n')
        sys.stdout.buffer.flush()
    except Exception as e:
        fallback_err = json.dumps({"status": "ERROR", "payload": f"Критический сбой IPC: {str(e)}"}, ensure_ascii=False)
        sys.stdout.buffer.write(fallback_err.encode('utf-8', errors='ignore') + b'\n')
        sys.stdout.buffer.flush()

def main():
    try:
        input_bytes = sys.stdin.buffer.read()
        if not input_bytes:
            return
            
        input_data = input_bytes.decode('utf-8', errors='replace')
        params = json.loads(input_data)
        
        model_path = params["model_path"]
        system_prompt = sanitize_text(params.get("system_prompt", ""))
        user_text = sanitize_text(params.get("user_text", ""))
        
        n_threads = params["n_threads"]
        n_ctx = params["n_ctx"]
        max_tokens = params["max_tokens"]
        
        if not os.path.exists(model_path):
            send_json_to_parent({"status": "ERROR", "payload": f"Файл модели не найден по пути:\n{model_path}"})
            return

        try:
            from llama_cpp import Llama
        except ImportError as e:
            send_json_to_parent({
                "status": "ERROR", 
                "payload": f"Ошибка инициализации LLM: модуль 'llama_cpp' не найден.\nЕсли вы запускаете из исходников, выполните: pip install llama-cpp-python\nДетали: {e}"
            })
            return
        
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=0,        
            chat_format="chatml",  
            verbose=False,
        )

        system_tokens = llm.tokenize(system_prompt.encode("utf-8", errors="replace"))
        reserved = len(system_tokens) + max_tokens + 32  
        token_budget = max(n_ctx - reserved, 64)

        user_tokens = llm.tokenize(user_text.encode("utf-8", errors="replace"))
        truncated = len(user_tokens) > token_budget
        if truncated:
            user_tokens = user_tokens[:token_budget]
            user_text = llm.detokenize(user_tokens).decode("utf-8", errors="ignore")

        strict_system_prompt = system_prompt + " Опирайся ТОЛЬКО на предоставленный текст. Не придумывай ничего от себя."
        framed_user_text = f"Проанализируй следующий текст и составь его краткое содержание (выдели главные мысли):\n\n---\n{user_text}\n---\n\nКраткое содержание:"

        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": strict_system_prompt},
                {"role": "user", "content": framed_user_text},
            ],
            max_tokens=max_tokens,
            temperature=0.1,          
            top_p=0.9,               
            repeat_penalty=1.1,       
            stop=["<|im_end|>"],
        )

        summary_text = response["choices"][0]["message"]["content"].strip()
        if truncated:
            summary_text += (f"\n\n[!] Внимание: Текст транскрипта превышал контекстное окно "
                              f"модели (limit n_ctx={n_ctx}) и был автоматически обрезан.")

        send_json_to_parent({"status": "DONE", "payload": summary_text})

    except Exception:
        send_json_to_parent({"status": "ERROR", "payload": traceback.format_exc()})

if __name__ == "__main__":
    main()