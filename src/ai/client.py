"""
DeepSeek API 客户端
复用 OpenAI SDK，针对 DeepSeek v4 Pro 优化创意写作
"""
from openai import OpenAI


class DeepSeekClient:
    """DeepSeek API 客户端，封装 OpenAI 兼容接口"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-pro",
    ):
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.85,
        max_tokens: int = 8192,
        top_p: float = 0.92,
        frequency_penalty: float = 0.5,
        presence_penalty: float = 0.3,
        disable_thinking: bool = True,
    ) -> str:
        """
        发送 Chat Completion 请求

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 生成温度 (0-2)，创意写作推荐 0.85
            max_tokens: 最大输出 token 数
            top_p: 核采样参数
            frequency_penalty: 频率惩罚 (-2 到 2)，减少重复
            presence_penalty: 存在惩罚 (-2 到 2)，鼓励新话题
            disable_thinking: 是否禁用 thinking mode（创意写作需要禁用，
                             否则 temperature/top_p 等参数会被忽略）

        Returns:
            AI 生成的文本
        """
        extra_body = {}
        if disable_thinking:
            extra_body["thinking"] = {"type": "disabled"}

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )

        return response.choices[0].message.content or ""

    def chat_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        **kwargs,
    ) -> str:
        """
        带重试的 Chat Completion 请求

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            max_retries: 最大重试次数
            **kwargs: 传递给 chat() 的其他参数

        Returns:
            AI 生成的文本

        Raises:
            RuntimeError: 所有重试均失败
        """
        import time

        last_error = None
        for attempt in range(max_retries):
            try:
                return self.chat(system_prompt, user_prompt, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                    print(f"  [API] 重试 {attempt + 1}/{max_retries}，等待 {wait}s... ({e})")
                    time.sleep(wait)

        raise RuntimeError(f"API 调用失败（{max_retries} 次重试后）: {last_error}")
