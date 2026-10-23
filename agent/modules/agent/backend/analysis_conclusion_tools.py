"""Dynamic enum schemas for the host-owned conclusion submission tool."""
from typing import Literal
from pydantic import Field, create_model


def restrict_schema(tool, tools):
    from .analysis_crossspecies import conclusion_scope_options

    options = conclusion_scope_options(tools)
    values = tuple(options)
    if not values:
        raise ValueError("No registered conclusion scope is available")
    meaning = "; ".join(key + ": " + value for key, value in options.items())
    schema = create_model(
        "CurrentPlanConclusion",
        __base__=tool.args_schema,
        claim_scope=(Literal[values], Field(description=meaning)),
    )
    return tool.model_copy(update={
        "args_schema": schema,
        "description": "Submit a conclusion using one current allowed scope. " + meaning
                       + " Rejections explain the allowed values. At most 4 distinct submissions.",
    })
