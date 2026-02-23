from typing import List
from datetime import datetime
import requests
from PyPDF2 import PdfReader
import os
import feedparser
import traceback

from utils.paper import Paper

class PaperSource:
    def search():
        raise NotImplementedError
    
    def download_pdf():
        raise NotImplementedError
    
    def read_paper():
        raise NotImplementedError
    
class ArxivSearch(PaperSource):
    """Searcher for arXiv papers"""
    BASE_URL = "http://export.arxiv.org/api/query"

    def search(self, query: str = "", max_results: int = 10):
        params = {
            "search_query": query,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending"
        }

        response = requests.get(self.BASE_URL, params=params)
        feed = feedparser.parse(response.content)
        papers = []

        for entry in feed.entries:
            try:
                authors = [author.name for author in entry.authors]
                published = datetime.strptime(entry.published, "%Y-%m-%dT%H:%M:%SZ")
                updated = datetime.strptime(entry.updated, "%Y-%m-%dT%H:%M:%SZ")
                pdf_url = next((link.href for link in entry.links if link.type == "application/pdf"), "")
                papers.append(Paper(
                    paper_id=entry.id.split('/')[-1],
                    title=entry.title,
                    authors=authors,
                    abstract=entry.summary,
                    url=entry.id,
                    pdf_url=pdf_url,
                    published_date=published,
                    updated_date=updated,
                    source="ArXiv",
                    categories=[tag.term for tag in entry.tags],
                    keywords=[],
                    doi=entry.get('doi', '')
                ))
            except Exception as e:
                print(e)
                print(traceback.format_exc())

        return papers
    
    def download_pdf(self, paper_id: str, save_path: str):
        pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
        response = requests.get(pdf_url)
        output_file = f"{save_path}/{paper_id}.pdf"
        with open(output_file, "wb") as f:
            f.write(response.content)
        
        return output_file
    
    def read_paper(self, paper_id: str, save_path: str = ".download/"):
        """
        read a paper and convert it to text format
        
        :param paper_id: arXiv paper id
        :type paper_id: str
        :param save_apth: path to save paper in the format of text
        :type save_apth: str

        :return: the extracted content in the format of text from pdf
        :type return: str
        """
        pdf_path = f"{save_path}/{paper_id}.pdf"
        if not os.path.exists(pdf_path):
            pdf_path = self.download_pdf(paper_id, save_path)

        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"

            return text.strip()
        
        except Exception as e:
            print(f"Error: {paper_id}")
            print(traceback.format_exc())
            return ""
