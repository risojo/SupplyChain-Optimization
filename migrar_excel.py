import os
import pandas as pd

# 1. Rutas de origen y destino
DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))
ARCHIVOS_ORIGEN = [
    os.path.join(DIRECTORIO_ACTUAL, "archivo2.xlsx"),
    os.path.join(DIRECTORIO_ACTUAL, "archivo 2.xlsx")
]
NUEVO_ARCHIVO_PATH = os.path.join(DIRECTORIO_ACTUAL, "LRI_data.xlsx")

# 2. Diccionario exacto de traducción basado en tu imagen
DICCIONARIO_COLUMNAS = {
    "cod_producto": "codigo",
    "cat_producto": "categoria",
    "subcat_producto": "subcategoria",
    "desc_producto": "descripcion",
    "proveedor": "proveedor",
    "pais": "pais",
    "empaque": "empaque",
    "bultos/tarima": "bultos tarima",
    "cubicaje/tarima": "cubicaje tarima",
    "demanda_mes1": "demanda mes 1",
    "demanda_mes2": "demanda mes 2",
    "demanda_mes3": "demanda mes 3",
    "demanda_mes4": "demanda mes 4",
    "demanda_mes5": "demanda mes 5",
    "demanda_mes6": "demanda mes 6",
    "demanda_mes7": "demanda mes 7",
    "demanda_mes8": "demanda mes 8",
    "demanda_mes9": "demanda mes 9",
    "demanda_mes10": "demanda mes 10",
    "demanda_mes11": "demanda mes 11",
    "demanda_mes12": "demanda mes 12",
    "ordenes_anual": "ordenes anual",
    "t_entrega_prom": "tiempo entrega",
    "inv_final/bultos": "inventario final bulto",
    "inv_prom/bultos": "inventario promedio bultos",
    "inv_trans/bultos": "valor inventario transito",
    "precio_uni/bulto": "precio unitario bulto",
    "costo_uni/bulto": "costo unitario bulto",
    "factor_escazes": "factor escazes",
    "unidades_vendidas": "unidades vendidas",
    "bultos_vendidos": "bultos vendidos",
    "margen_utilidad/ventas": "margen utilidad ventas",
    "ventas_totales": "ventas totales",
    "ventas_al_costo": "ventas costo",
    "margen_bruto": "margen bruto total",
    "valor_inv_prom_bultos": "valor inventario promedio",
    "rotacion": "rotacion",
    "meses_inv": "meses inventario",
    "prom_bultos_desp/mes": "bultos despachados mes",
    "cubicaje_inv_prom": "cubicaje inventario",
    "ICR": "costo mantener inventario",
    "Fac. Escazes": "factor escazes",
    "Factor escazes": "factor escazes",
    "EVAI": "EVAI",
    "Tipo": "clase"
}

def ejecutar_migracion():
    archivo_encontrado = None
    for ruta in ARCHIVOS_ORIGEN:
        if os.path.exists(ruta):
            archivo_encontrado = ruta
            break
            
    if not archivo_encontrado:
        print("❌ Error: No se encontró 'archivo2.xlsx' ni 'archivo 2.xlsx' en esta carpeta.")
        return

    print(f"📖 Leyendo archivo original: {os.path.basename(archivo_encontrado)}...")
    df = pd.read_excel(archivo_encontrado, engine="openpyxl")
    
    # Renombrar columnas existentes según el diccionario
    print("🔄 Renombrando columnas internamente...")
    df.rename(columns=DICCIONARIO_COLUMNAS, inplace=True)
    
    # Guardar en el nuevo archivo profesional
    print(f"💾 Guardando nuevo archivo como: LRI_data.xlsx...")
    df.to_excel(NUEVO_ARCHIVO_PATH, index=False, engine="openpyxl")
    print("✅ ¡Migración completada con éxito!")

if __name__ == "__main__":
    ejecutar_migracion()