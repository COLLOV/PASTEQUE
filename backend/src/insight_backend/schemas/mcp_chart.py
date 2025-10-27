from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChartDataset(BaseModel):
    sql: str = Field(..., min_length=1, description="Requête SQL exécutée pour obtenir les données.")
    columns: List[str] = Field(default_factory=list, description="Colonnes retournées par la requête SQL.")
    rows: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Lignes issues de la requête SQL, limitées côté serveur pour éviter les dépassements.",
    )
    row_count: Optional[int] = Field(
        default=None,
        description="Nombre total de lignes retournées par la requête (avant troncature).",
    )
    step: Optional[int] = Field(
        default=None,
        description="Étape NL→SQL (si plan multi-requêtes)."
    )
    description: Optional[str] = Field(
        default=None,
        description="Contexte facultatif sur l'usage de cette requête."
    )


class ChartRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Instruction utilisateur pour le graphique")
    answer: str | None = Field(
        default=None,
        description="Réponse textuelle générée avant la demande de graphique."
    )
    dataset: ChartDataset = Field(
        ...,
        description="Résultat SQL (colonnes + lignes) utilisé pour dériver le graphique."
    )


class ChartResponse(BaseModel):
    prompt: str
    chart_url: str
    tool_name: str
    chart_title: str | None = None
    chart_description: str | None = None
    chart_spec: Dict[str, Any] | None = None
    source_sql: str | None = Field(
        default=None,
        description="Requête SQL ayant servi à construire le graphique."
    )
    source_row_count: int | None = Field(
        default=None,
        description="Nombre de lignes disponibles dans le résultat SQL d'origine."
    )
