"""Generate a sample output document to validate the format with the team."""

from pathlib import Path

from patent_retriever.domain.models import (
    Claim,
    Paragraph,
    PatentDocument,
    RenderOptions,
)
from patent_retriever.renderers.docx_renderer import render_text, write_docx

document = PatentDocument(
    publication_number="US20250097171A1",
    title="SYSTEM AND METHOD FOR SAMPLE GENERATION",
    inventors=("Jane Doe",),
    abstract="A system is disclosed for generating samples.",
    abstract_figure_reference="Fig. 1.",
    background=(Paragraph(number=1, text="Existing approaches are inadequate."),),
    summary=(Paragraph(number=2, text="The invention addresses this."),),
    brief_description_of_drawings=(Paragraph(number=3, text="FIG. 1 shows the system."),),
    detailed_description=(
        Paragraph(number=4, text="Referring to FIG. 1, the system (100) operates."),
    ),
    claims=(
        Claim(number=1, text="A method comprising: generating a sample."),
        Claim(number=2, text="The method of claim 1, wherein the sample is textual."),
    ),
)

options = RenderOptions(
    attorney_docket_number="ARM-0001",
    client_reference="CR-2026-01",
)

print(render_text(document, options))
path = write_docx(document, Path("output/sample.docx"), options)
print(f"\n-> {path}")
