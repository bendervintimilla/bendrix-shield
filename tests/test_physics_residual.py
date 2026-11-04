"""M6: detector de sensor falsificado por residuo físico.

Series sintéticas (simulated) generadas con un integrador de dos nodos
en el propio test, ruido gaussiano con semilla fija, sin red.
La tasa de falsos positivos se mide sobre series legítimas con ruido.
"""

from __future__ import annotations

import random

from shield.physics.contract import ColdRoomParams, RoomState
from shield.physics.residual import THRESHOLD_C, check_sensor

PARAMS = ColdRoomParams()
DT_MIN = 1.0


def _truth_series(
    minutes: int,
    *,
    door_open: bool = False,
    compressor_mode: str = "thermostat",
) -> tuple[list[RoomState], list[float]]:
    """Genera historial y temperatura real del aire (integrador del test)."""
    air, product = 3.0, 3.0
    on = False
    states: list[RoomState] = []
    truth: list[float] = []
    for i in range(minutes):
        if compressor_mode == "off":
            on = False
        elif compressor_mode == "on":
            on = True
        elif air > 3.0 + 0.5:
            on = True
        elif air < 3.0 - 0.5:
            on = False
        states.append(
            RoomState(
                t_min=float(i),
                air_c=air,
                product_c=product,
                setpoint_c=3.0,
                compressor_on=on,
                door_open=door_open,
            )
        )
        truth.append(air)
        ua = PARAMS.ua_wall_w_per_k + (PARAMS.ua_door_open_w_per_k if door_open else 0.0)
        ha = PARAMS.ha_air_product_w_per_k * 2.0  # 200 kg / 100 kg
        c_prod = 200.0 * PARAMS.product_cp_j_per_kgk
        for _ in range(2):  # subpasos de 30 s
            d_air = (
                ua * (PARAMS.ambient_c - air)
                + ha * (product - air)
                - (PARAMS.cooling_capacity_w if on else 0.0)
            ) / PARAMS.air_mass_j_per_k
            d_prod = ha * (air - product) / c_prod
            air += d_air * 30.0
            product += d_prod * 30.0
    return states, truth


def test_spoofing_plano_compresor_apagado_puerta_abierta():
    """El sensor dice 3.0 °C plano con compresor apagado y puerta abierta."""
    states, truth = _truth_series(120, door_open=True, compressor_mode="off")
    assert truth[-1] > 6.0  # la física real sube: el plano es imposible
    out = check_sensor(PARAMS, states, [3.0] * len(states))
    assert out["spoofed"] is True
    assert out["residual_c"] > THRESHOLD_C
    assert out["window_min"] >= 100.0
    assert out["explanation"]


def test_spoofing_con_offset_constante():
    """Lo reportado sigue la forma real pero corrido +3 °C."""
    states, truth = _truth_series(120)
    reported = [t + 3.0 for t in truth]
    out = check_sensor(PARAMS, states, reported)
    assert out["spoofed"] is True
    assert out["mean_abs_residual_c"] > THRESHOLD_C


def test_sensor_sano_con_ruido_gaussiano():
    """Sensor sano: verdad + ruido gaussiano sigma 0.3, semilla fija."""
    states, truth = _truth_series(120)
    rng = random.Random(42)
    reported = [t + rng.gauss(0.0, 0.3) for t in truth]
    out = check_sensor(PARAMS, states, reported)
    assert out["spoofed"] is False
    assert out["residual_c"] < THRESHOLD_C


def test_sensor_congelado_stuck():
    """El sensor queda clavado en el valor inicial mientras el aire sube."""
    states, truth = _truth_series(120, door_open=True, compressor_mode="off")
    reported = [truth[0]] * len(states)
    out = check_sensor(PARAMS, states, reported)
    assert out["spoofed"] is True
    assert out["stuck"] is True


def test_tasa_falsos_positivos_medida():
    """FPR sobre 200 series legítimas con ruido gaussiano (semilla fija).

    Resultado esperado con THRESHOLD_C=2.0 y sigma=0.3: 0/200.
    Se exige tasa <= 0.05 para dejar margen al cambiar el gemelo M1.
    """
    rng = random.Random(20261104)
    false_positives = 0
    trials = 200
    for _ in range(trials):
        states, truth = _truth_series(120)
        reported = [t + rng.gauss(0.0, 0.3) for t in truth]
        if check_sensor(PARAMS, states, reported)["spoofed"]:
            false_positives += 1
    rate = false_positives / trials
    assert rate <= 0.05, f"FPR medida {rate:.3f} ({false_positives}/{trials})"


def test_sin_datos_no_marca_ni_revienta():
    """Entradas vacías o de un solo punto: sin marca, sin excepción."""
    out = check_sensor(PARAMS, [], [])
    assert out["spoofed"] is False
    assert out["residual_c"] == 0.0
    states, truth = _truth_series(1)
    assert check_sensor(PARAMS, states, truth)["spoofed"] is False


def test_dict_con_claves_del_contrato():
    """El dict trae spoofed, residual_c, ventana y explicación de una frase."""
    states, truth = _truth_series(60)
    out = check_sensor(PARAMS, states, truth)
    assert isinstance(out["spoofed"], bool)
    assert isinstance(out["residual_c"], float)
    assert out["ventana_min"] == out["window_min"]
    assert out["explanation"].count(".") <= 2  # una frase (más el decimal)
