# Atajo: Inventarios
$raiz = $PSScriptRoot
Set-Location $raiz
& "$raiz\.venv\Scripts\python.exe" -m streamlit run modules/inventarios/inventario_app.py
