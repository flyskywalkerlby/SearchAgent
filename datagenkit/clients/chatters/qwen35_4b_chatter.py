from openai import OpenAI
import os

os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:8000/v1"
os.environ["OPENAI_API_KEY"] = "EMPTY"

client = OpenAI()

messages = [
    {"role": "system", "content": "你是一个有帮助的中文助手。回答简洁、直接。"}
]

print("输入内容后回车即可发送；输入 exit 退出。")

while True:
    user_text = input("\n你: ").strip()

    if not user_text:
        continue

    if user_text.lower() == "exit":
        print("已退出。")
        break

    messages.append({"role": "user", "content": user_text})

    try:
        stream = client.chat.completions.create(
            model="qwen3.5-4b",
            messages=messages,
            max_tokens=512,
            temperature=1.0,
            top_p=0.95,
            presence_penalty=1.5,
            stream=True,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False
                },
                "top_k": 20,
            },
        )

        print("\n助手: ", end="", flush=True)

        reply_parts = []

        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta is None:
                continue

            text = delta.content
            if text:
                print(text, end="", flush=True)
                reply_parts.append(text)

        reply = "".join(reply_parts)
        print()

        messages.append({"role": "assistant", "content": reply})

    except KeyboardInterrupt:
        print("\n[已中断本次生成]")
        messages.pop()
    except Exception as e:
        print(f"\n[请求失败] {e}")
        messages.pop()
        