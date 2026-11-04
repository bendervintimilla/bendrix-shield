"""Último estado seguro: acción reversible de contención automática.

Regla de ORDENES.md: «contain first, ask later». Ante una acción
bloqueada, el autopiloto (M10) no espera al dueño para lo reversible:
devuelve el equipo a su setpoint de fábrica. Restaurar un setpoint es
reversible en segundos (el dueño puede deshacerlo) y, al reemplazar el
control vigente, cancela un deshielo o un apagado forzado en curso: el
compresor vuelve a gobernarse por el termostato (enciende si el aire
está sobre el setpoint). Lo irreversible nunca pasa por aquí.
"""

from __future__ import annotations

from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.presets import FACTORY_SETPOINT_C


def factory_setpoint_c(params: ColdRoomParams) -> float:
    """Setpoint de fábrica del equipo, en °C.

    Para un equipo sin preset conocido se usa el punto medio de su
    envolvente segura: supuesto conservador, rotulado como tal.
    """
    if params.name in FACTORY_SETPOINT_C:
        return FACTORY_SETPOINT_C[params.name]
    return (params.safe_min_c + params.safe_max_c) / 2.0


def last_safe_action(params: ColdRoomParams, state: RoomState) -> ProposedAction:
    """Acción reversible que deja el equipo en su último estado seguro.

    Es un ``set_setpoint`` al valor de fábrica. El ejecutor que la
    aplique debe, en el mismo acto, cancelar cualquier deshielo o
    ``compressor_off`` en curso: el contrato solo expresa la orden como
    setpoint, y la cancelación es parte de reemplazar el control.
    ``state`` se recibe para firmar igual que el resto del escudo y
    para que el llamador deje claro sobre qué equipo actúa; el valor
    devuelto no depende del setpoint actual (pudo ser manipulado).

    Ojo: esta acción sola no trae privilegio. El autopiloto debe
    pedirla por ``shield.physics.rescue.issue_last_safe_action``,
    que la devuelve junto a su grant firmado; sin grant válido el
    gate la trata como cualquier otra acción.
    """
    return ProposedAction(
        kind="set_setpoint",
        equipment=params.name,
        value=factory_setpoint_c(params),
        duration_min=0.0,
        start_in_min=0.0,
        requested_by="wairrior-autopilot",
        source="schedule",
        note=(
            "reversible: restaura el setpoint de fábrica y cancela "
            "deshielo/apagado en curso; el compresor vuelve al termostato"
        ),
    )
