from sqlmodel import SQLModel


# Data model used for requests/responses in the application.
# Legal document model for indexing to and from elasticsearch
class LegalDocumentBase(SQLModel):
    tittle: str
    content: str
    resource_url: str


class LegalDocumentCreate(LegalDocumentBase):
    pass


class LegalDocumentRead(LegalDocumentBase):
    str: int
