from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional

@dataclass
class Paper:
    "standardized paper format with core fields for academic sources"
    paper_id: str
    title: str
    authors: List[str]
    abstract: str
    doi: str
    published_date: datetime
    pdf_url: str
    url: str
    source: str

    # optional
    updated_date: Optional[datetime] = None
    categories: List[str] = None
    keywords: List[str] = None
    citations: int = 0
    references: Optional[List[str]] = None
    extra: Optional[Dict] = None

    def __post_init__(self):
        """Post-initialization to handle default values"""
        if self.authors is None:
            self.authors = []
        if self.categories is None:
            self.categories = []
        if self.keywords is None:
            self.keywords = []
        if self.references is None:
            self.references = []
        if self.extra is None:
            self.extra = {}

    def to_dict(self) -> Dict:
        """Convert paper to dictionary format for serialization"""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": "; ".join(self.authors) if self.authors else " ",
            "doi": self.doi,
            "published_date": self.published_date.isoformat() if self.published_date else '',
            "pdf_url": self.pdf_url,
            "url": self.url,
            "source": self.source,
            "updated_date": self.updated_date.isoformat() if self.updated_date else '',
            'categories': '; '.join(self.categories) if self.categories else '',
            'keywords': '; '.join(self.keywords) if self.keywords else '',
            'citations': self.citations,
            'references': '; '.join(self.references) if self.references else '',
            'extra': str(self.extra) if self.extra else ''
        }
