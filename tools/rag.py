from typing import Union
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, get_buffer_string
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import os
import requests
import traceback
import time

from loguru import logger

def perform_rerank(all_docs_str: list[str], query: str, max_token_cnt: int):
    if len(query) > 2000:
        logger.warning("query is too long, truncated to 2000 characters", query[:2000])
        query = query[:2000]

    all_messages_with_score = []
    all_docs_chunks = [all_docs_str[i:(i+32)] for i in range(0, len(all_docs_str), 32)]

    for doc_chunks in all_docs_chunks:
        input_doc_list = doc_chunks
        payload = {
            "model": os.environ.get("RERANK_MODEL", "bge-reranker-v2-m3"),
            "query": query,
            "documents": input_doc_list,
            "return_raw_scores": True
        }

        api_key = os.environ.get("RERANK_API_KEY", "")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        url = os.environ.get("RERANK_BASE_URL", "https://cloud.infini-ai.com/maas/v1/") + "rerank"
        messages_with_score = []

        for try_i in range(10):
            response = requests.post(url, json=payload, headers=headers)
            try:
                for res in response.json()["results"]:
                    if ("document" in res) and isinstance(res["document"], str):
                        messages_with_score.append(
                            {
                                "text": res["document"],
                                "score": res["relevance_score"]
                            }
                        )
                    elif ("document" in res) and ("text" in res["document"]) and \
                        isinstance(res["document"], dict) and isinstance(res["document"]["text"], str):
                        messages_with_score.append(
                            {
                                "text": res["document"]["text"],
                                "score": res["relevance_score"]
                            }
                        )
                    elif ("index" in res):
                        messages_with_score.append(
                            {
                                "text": input_doc_list[int(res["index"])],
                                "score": res["relevance_score"]
                            }
                        )
                    else:
                        raise ValueError("Invalid document type")
                    
            except Exception as e:
                logger.warning("something wrong!!!", e)
                logger.warning(traceback.format_exc())
                logger.warning(f"Retrying... {try_i+1}/10")
                logger.warning(response.json())
                time.sleep(10)

            else:
                break
        
        if not messages_with_score:
            logger.warning("Rerank failed, setting score to 0.0")
            for doc_str in all_docs_str:
                messages_with_score = [{"text": doc_str, "score": 0.0}]

        all_messages_with_score.extend(messages_with_score)
    
    # 降序排列
    all_messages_with_score = sorted(all_messages_with_score, key=lambda x: x["score"], reverse=True)
    logger.info(f"All rerank scores: {[m['score'] for m in all_messages_with_score]}")

    all_messages = []
    current_token_cnt = 0
    for message_with_score in all_messages_with_score:
        current_token_cnt += count_tokens_approximately([HumanMessage(content=message_with_score["text"])])
        if current_token_cnt  > max_token_cnt:
            break

        all_messages.append(HumanMessage(content=message_with_score["text"]))

    return all_messages


def vector_search(messages: Union[list, str], query: str, token_cnt: int = 10000):

    if isinstance(messages, str):
        messages = [HumanMessage(content=messages)]

    this_token_cnt = count_tokens_approximately(messages)
    if this_token_cnt < token_cnt:
        logger.info(f"No need to use vector search, because token count {this_token_cnt} is less than {token_cnt}")

    text_spiliter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=500)

    all_docs = []
    for message in messages:
        message_texts = get_buffer_string([message])
        message_doc = Document(page_content=message_texts)
        all_splits = text_spiliter.split_documents([message_doc])
        all_docs.extend(all_splits)

    all_docs_str = [doc.page_content for doc in all_docs]
    logger.info(f"All split document length: {str([len(doc) for doc in all_docs_str])}")

    relevant_messages = perform_rerank(all_docs_str, query, token_cnt)

    logger.info(f"Message number: {len(messages)}, split number: {len(all_docs)}, "
                f"Relevant message number: {len(relevant_messages)}")
    return relevant_messages[::-1]
