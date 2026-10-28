# crew/

Cliente cero de la demo: `orchestrator.py` (Spark 1.3 con tool calling)
más `compras/` (factura -> costo, Spark visión) y `bodega/` (conteo con
SAM 3.1 + voz). Todo vía SDK (`wrap`, `@shield.tool`, `untrusted`) y
gateway, con un token por agente (`build_crew`). Sin créditos corre en
replay con el router local determinista. Lo construyó H7.
