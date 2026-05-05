import os
import json
from http import HTTPStatus
from dotenv import load_dotenv
import dashscope
from langchain_openai import ChatOpenAI

load_dotenv()


llm = ChatOpenAI(
    model="qwen3.6-flash",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0.1,
    timeout=300,  # 5分钟超时
    max_retries=2,
)

# llm_response = llm.stream("写一个hello world的代码？")

# for chunk in llm_response:
    # print(chunk.content, end="", flush=True)


# Multimodal LLM (Vision) - OpenAI compatible interface
# 支持图片理解的多模态大模型客户端
mllm = ChatOpenAI(
    model="qwen3.6-flash", 
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0.1,
    timeout=300,
    max_retries=2,
)


def get_embedding(text: str) -> list[float] | None:
    """Vectorize text via Dashscope tongyi-embedding-vision-plus (text only)."""
    try:
        resp = dashscope.MultiModalEmbedding.call(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            model="tongyi-embedding-vision-flash-2026-03-06",
            input=[{"text": text}],
        )
        if resp.status_code != HTTPStatus.OK:
            return None
        return resp.output["embeddings"][0]["embedding"]
    except Exception:
        return None


def call_mllm_image(image_url: str, prompt: str = "描述这张图片") -> str:
    """
    调用多模态大模型分析图片

    参数:
        image_url: 图片URL或base64数据URI
        prompt: 给模型的指令

    返回:
        模型对图片的描述/分析结果
    """
    response = mllm.stream([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        }
    ])

    output = ""
    for chunk in response:
        print(chunk.content, end="", flush=True)
        output += chunk.content
    return output


if __name__ == "__main__":
    emb = get_embedding("帕累托图画一个")
    print(f"embedding dimension: {len(emb) if emb else 'FAILED'}")
    if emb:
        print(f"first 5 values: {emb[:5]}")
