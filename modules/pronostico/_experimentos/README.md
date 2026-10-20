# Experimento → producción: distribución estilo @RISK

Los helpers (`sync_linea_helpers.py`) y la vista interactiva ya están
integrados en **Forecast Pro** (`pronostico_app.py` → botón «Simulación Monte Carlo»).

## Qué hace en producción

1. Campo de bultos + slider → delimitador derecho.
2. **Camino inverso:** probabilidad objetivo (`inv_cdf`) → actualiza bultos y delimitadores.
3. **Histograma estilo @RISK:** slider de rango con dos mangos; barras **anaranjadas**
   en el centro y más claras en las colas; franja superior con % izquierda / centro / derecha.

No altera el motor de `pronostico_calculos.py` ni el Excel.

## Copia de laboratorio (puerto aparte, opcional)

```bash
streamlit run modules/pronostico/_experimentos/pronostico_app_exp_linea_demanda.py --server.port 8503
```

Producción:

```bash
streamlit run modules/pronostico/pronostico_app.py
```

## Prueba unitaria

```bash
python -m unittest modules/pronostico/_experimentos/test_sync_linea_demanda.py
```
