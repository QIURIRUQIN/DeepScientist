"""统一的LLM配置模块，支持多种模型"""
import os
from typing import Optional, Any
from common.utils import init_logger

logger = init_logger("llm_config")

# 使用 langchain 的统一接口
try:
    from langchain.chat_models import init_chat_model
except ImportError:
    try:
        from langchain_core.chat_models import init_chat_model
    except ImportError:
        raise ImportError("请安装 langchain 包以使用 init_chat_model")


def get_llm(
    provider: str = "deepseek",
    model_name: Optional[str] = None,
    temperature: float = 0.7,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Any:
    """
    获取配置好的LLM实例，使用 langchain 的 init_chat_model 统一接口
    
    Args:
        provider: 模型提供商，支持 "deepseek", "openai" 等
        model_name: 模型名称，如果为None则使用默认值
        temperature: 温度参数
        api_key: API密钥，如果为None则从环境变量获取
        base_url: API基础URL，如果为None则使用默认值（仅对DeepSeek等需要自定义base_url的模型有效）
    
    Returns:
        配置好的LLM实例
    """
    provider = provider.lower()
    
    # 根据provider设置默认值
    if provider == "deepseek":
        default_model = model_name or "deepseek-chat"
        default_base_url = base_url or "https://api.deepseek.com/v1"
        default_api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        
        if not default_api_key:
            logger.warning("未设置DEEPSEEK_API_KEY环境变量，请确保已设置API密钥")
        
        # DeepSeek使用OpenAI兼容的API，需要自定义base_url
        # 尝试使用 init_chat_model，通过 kwargs 传递自定义参数
        try:
            # 设置环境变量
            if default_api_key:
                os.environ["OPENAI_API_KEY"] = default_api_key
            
            # 使用 init_chat_model，通过 kwargs 传递 base_url 和 api_key
            llm = init_chat_model(
                model=default_model,
                temperature=temperature,
                openai_api_key=default_api_key,
                openai_api_base=default_base_url,
            )
            
            # 如果 init_chat_model 没有正确处理 base_url，尝试手动设置
            if hasattr(llm, 'openai_api_base'):
                if not llm.openai_api_base or llm.openai_api_base != default_base_url:
                    llm.openai_api_base = default_base_url
            elif hasattr(llm, 'base_url'):
                llm.base_url = default_base_url
                
        except Exception as e:
            logger.warning(f"使用 init_chat_model 初始化 DeepSeek 失败: {e}，尝试使用 ChatOpenAI")
            # 如果 init_chat_model 失败，回退到直接使用 ChatOpenAI
            try:
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(
                    model=default_model,
                    temperature=temperature,
                    openai_api_key=default_api_key,
                    openai_api_base=default_base_url,
                )
            except ImportError:
                raise ImportError(
                    "无法初始化DeepSeek模型。请安装 langchain-openai: pip install langchain-openai"
                )
        
        logger.info(f"已配置DeepSeek模型: {default_model}, API: {default_base_url}")
        return llm
    
    elif provider == "openai":
        default_model = model_name or "gpt-3.5-turbo"
        default_api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not default_api_key:
            logger.warning("未设置OPENAI_API_KEY环境变量")
        else:
            os.environ["OPENAI_API_KEY"] = default_api_key
        
        # 使用 init_chat_model 统一接口
        try:
            llm = init_chat_model(
                model=default_model,
                temperature=temperature,
            )
        except Exception as e:
            logger.error(f"初始化OpenAI模型失败: {e}")
            raise
        
        logger.info(f"已配置OpenAI模型: {default_model}")
        return llm
    
    elif provider == "zhipu" or provider == "glm":
        # 智谱AI GLM模型支持
        default_model = model_name or "glm-4-flash-1.1v"  # 默认使用多模态模型
        default_base_url = base_url or "https://open.bigmodel.cn/api/paas/v4/"
        default_api_key = api_key or os.getenv("ZHIPU_API_KEY")
        
        if not default_api_key:
            logger.warning("未设置ZHIPU_API_KEY环境变量，请确保已设置API密钥")
        
        try:
            # 设置环境变量
            if default_api_key:
                os.environ["OPENAI_API_KEY"] = default_api_key
            
            # 使用 init_chat_model，通过 kwargs 传递 base_url 和 api_key
            llm = init_chat_model(
                model=default_model,
                temperature=temperature,
                openai_api_key=default_api_key,
                openai_api_base=default_base_url,
            )
            
            # 如果 init_chat_model 没有正确处理 base_url，尝试手动设置
            if hasattr(llm, 'openai_api_base'):
                if not llm.openai_api_base or llm.openai_api_base != default_base_url:
                    llm.openai_api_base = default_base_url
            elif hasattr(llm, 'base_url'):
                llm.base_url = default_base_url
                
        except Exception as e:
            logger.warning(f"使用 init_chat_model 初始化智谱模型失败: {e}，尝试使用 ChatOpenAI")
            # 如果 init_chat_model 失败，回退到直接使用 ChatOpenAI
            try:
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(
                    model=default_model,
                    temperature=temperature,
                    openai_api_key=default_api_key,
                    openai_api_base=default_base_url,
                )
            except ImportError:
                raise ImportError(
                    "无法初始化智谱模型。请安装 langchain-openai: pip install langchain-openai"
                )
        
        logger.info(f"已配置智谱模型: {default_model}, API: {default_base_url}")
        return llm
    
    else:
        raise ValueError(f"不支持的provider: {provider}. 支持: deepseek, openai, zhipu")


def call_llm(llm: Any, prompt: str, logger_instance: Optional[Any] = None) -> str:
    """
    统一调用LLM的方法，使用标准接口
    
    Args:
        llm: LLM实例（通过 init_chat_model 初始化）
        prompt: 输入提示（字符串）
        logger_instance: 日志记录器实例
    
    Returns:
        LLM的响应文本
    """
    from langchain_core.messages import HumanMessage
    
    log = logger_instance or logger
    
    try:
        # 使用标准的 invoke 方法，传入 HumanMessage
        message = HumanMessage(content=prompt)
        result = llm.invoke([message])
        
        # 提取响应内容
        if hasattr(result, 'content'):
            return result.content
        elif isinstance(result, str):
            return result
        else:
            return str(result)
            
    except Exception as e:
        log.error(f"调用LLM失败: {e}", exc_info=True)
        raise


def call_multimodal_llm(
    llm: Any, 
    prompt: str, 
    image_paths: Optional[list] = None,
    logger_instance: Optional[Any] = None
) -> str:
    """
    调用多模态LLM的方法，支持图片输入
    
    Args:
        llm: LLM实例（多模态模型，如GLM-4.1v）
        prompt: 输入提示（字符串）
        image_paths: 图片路径列表，支持本地文件路径
        logger_instance: 日志记录器实例
    
    Returns:
        LLM的响应文本
    """
    from langchain_core.messages import HumanMessage
    from pathlib import Path
    import base64
    
    log = logger_instance or logger
    
    try:
        # 构建消息内容
        content = [{"type": "text", "text": prompt}]
        
        # 添加图片
        if image_paths:
            for img_path in image_paths:
                img_file = Path(img_path)
                if not img_file.exists():
                    log.warning(f"图片文件不存在: {img_path}")
                    continue
                
                # 读取图片并转换为base64
                with open(img_file, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                
                # 根据文件扩展名确定MIME类型
                ext = img_file.suffix.lower()
                if ext == '.png':
                    mime_type = 'image/png'
                elif ext in ['.jpg', '.jpeg']:
                    mime_type = 'image/jpeg'
                elif ext == '.gif':
                    mime_type = 'image/gif'
                elif ext == '.webp':
                    mime_type = 'image/webp'
                else:
                    mime_type = 'image/png'  # 默认
                
                # 添加图片到内容中（使用data URI格式）
                image_url = f"data:{mime_type};base64,{image_data}"
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
        
        # 创建消息并调用
        message = HumanMessage(content=content)
        result = llm.invoke([message])
        
        # 提取响应内容
        if hasattr(result, 'content'):
            return result.content
        elif isinstance(result, str):
            return result
        else:
            return str(result)
            
    except Exception as e:
        log.error(f"调用多模态LLM失败: {e}", exc_info=True)
        raise
