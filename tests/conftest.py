"""Shared test fixtures."""

import pytest

from patent_retriever.domain.models import Claim, Paragraph, PatentDocument


@pytest.fixture
def minimal_document() -> PatentDocument:
    """The smallest valid PatentDocument."""
    return PatentDocument(
        publication_number="US20250097171A1",
        title="A Method For Testing Things",
        claims=(Claim(number=1, text="A method comprising: testing a thing."),),
    )


@pytest.fixture
def full_document() -> PatentDocument:
    """A document with content in every body section, using non-continuous numbering."""
    return PatentDocument(
        publication_number="US20250097171A1",
        title="A Method For Testing Things",
        inventors=("Jane Doe", "John Smith"),
        abstract="A method for testing things is disclosed.",
        abstract_figure_reference="Fig. 1.",
        background=(Paragraph(number=1, text="Prior art is inadequate."),),
        summary=(Paragraph(number=5, text="The invention solves this."),),
        brief_description_of_drawings=(
            Paragraph(number=9, text="FIG. 1 shows a testing apparatus."),
        ),
        detailed_description=(
            Paragraph(number=12, text="Referring to FIG. 1, the apparatus (100) operates."),
            Paragraph(number=13, text="The controller (101) coordinates operation."),
        ),
        claims=(
            Claim(number=1, text="A method comprising: testing a thing."),
            Claim(number=2, text="The method of claim 1, wherein the thing is a widget."),
        ),
    )
