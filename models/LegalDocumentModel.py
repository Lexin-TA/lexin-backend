from datetime import datetime

from sqlmodel import SQLModel


# Data model used for requests/responses in the application.
# Legal document model for indexing to and from elasticsearch
class LegalDocumentBase(SQLModel):
    title: str
    jenis_bentuk_peraturan: str
    pemrakarsa: str
    nomor: int
    tahun: int
    tentang: str
    tempat_penetapan: str
    ditetapkan_tanggal: datetime | None
    status: str
    dicabut_oleh: list[str]

    filename: str
    content: str
    resource_url: str
    reference_url: str


class LegalDocumentCreate(LegalDocumentBase):
    pass


class LegalDocumentRead(LegalDocumentBase):
    pass


# Elasticsearch mappings used for initial index creation of legal documents.
ELASTICSEARCH_LEGAL_DOCUMENT_MAPPINGS = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "jenis_bentuk_peraturan": {"type": "keyword"},
            "pemrakarsa": {"type": "keyword"},
            "nomor": {"type": "integer"},
            "tahun": {"type": "integer"},
            "tentang": {"type": "text"},
            "tempat_penetapan": {"type": "keyword"},
            "ditetapkan_tanggal": {"type": "date", "format": "yyyy-MM-dd"},
            "status": {"type": "keyword"},
            "dicabut_oleh": {"type": "text"},   # This is an array of document title strings.

            "filename": {"type": "keyword"},
            "content": {"type": "text"},
            "resource_url": {"type": "text"},
            "reference_url": {"type": "text"}
        }
    }
}
