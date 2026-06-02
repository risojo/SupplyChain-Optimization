"""Pipeline de datos: lectura y transformación, separados de la interfaz.

``loaders`` se ocupa de leer fuentes (Excel/CSV/uploads) y ``transform`` de
las transformaciones y métricas derivadas. Los módulos consumen estas
funciones en lugar de leer archivos directamente, para reutilizar lógica y
poder cambiar la fuente de datos en un solo lugar.
"""
