"""Modelos Pydantic (v2) da API."""
from typing import List, Optional

from pydantic import BaseModel, Field


# ---- Skills ----
class SkillIn(BaseModel):
    icon: str = Field(default="", max_length=80)
    title: str = Field(..., min_length=1, max_length=150)
    description: str = Field(default="", max_length=500)


class SkillOut(SkillIn):
    id: int
    position: int


# ---- Projetos ----
class ProjectLinkIn(BaseModel):
    label: str = Field(default="", max_length=80)
    href: str = Field(..., min_length=1, max_length=500)
    track: str = Field(default="", max_length=80)


class ProjectLinkOut(ProjectLinkIn):
    position: int


class ProjectIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=60, pattern=r"^[a-z0-9_\-]+$")
    icon: str = Field(default="", max_length=80)
    title: str = Field(..., min_length=1, max_length=150)
    description: str = Field(default="", max_length=600)
    published: bool = True
    techs: List[str] = Field(default_factory=list)
    links: List[ProjectLinkIn] = Field(default_factory=list)


class ProjectOut(BaseModel):
    id: str
    icon: str
    title: str
    description: str
    published: bool
    position: int
    image: str = ""
    techs: List[str]
    links: List[ProjectLinkOut]


# ---- Certificacoes ----
class CertificationIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=60, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(..., min_length=1, max_length=200)
    issuer: str = Field(default="", max_length=120)
    year: str = Field(default="", max_length=10)
    credential_id: str = Field(default="", max_length=60)
    url: str = Field(default="", max_length=500)


class CertImageOut(BaseModel):
    filename: str
    position: int


class CertificationOut(CertificationIn):
    position: int
    images: List[CertImageOut]


# ---- Conteudo do site ----
class SiteHero(BaseModel):
    greeting: str = ""
    title: str = ""
    tagline: str = ""
    tagline_highlight: str = ""
    description: str = ""


class SiteAbout(BaseModel):
    eyebrow: str = ""
    title: str = ""
    title_highlights: List[str] = Field(default_factory=list)
    paragraphs: List[str] = Field(default_factory=list)
    resume_url: str = ""


class SiteContact(BaseModel):
    title: str = ""
    title_highlight: str = ""
    description: str = ""
    whatsapp_number: str = ""
    whatsapp_display: str = ""


class SiteSocial(BaseModel):
    label: str = ""
    href: str = ""
    icon: str = ""
    track: str = ""


class SiteIn(BaseModel):
    hero: SiteHero = Field(default_factory=SiteHero)
    about: SiteAbout = Field(default_factory=SiteAbout)
    contact: SiteContact = Field(default_factory=SiteContact)
    social: List[SiteSocial] = Field(default_factory=list)


# ---- Ordenacao ----
class ReorderIn(BaseModel):
    ids: List[str]
