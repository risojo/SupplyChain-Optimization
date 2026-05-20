import streamlit as st
import streamlit_authenticator as stauth
import database

# Configuración de página
st.set_page_config(
    page_title="Scorecard Software",
    page_icon="🏗️",
    layout="wide"
)

def main():
    # 1. Obtener credenciales desde database.py
    try:
        credentials = database.fetch_all_users()
    except Exception as e:
        st.error(f"Error en la base de datos: {e}")
        return

    # 2. Configurar el Autenticador
    authenticator = stauth.Authenticate(
        credentials,
        "scorecard_software",
        "abcdef",
        cookie_expiry_days=30
    )

    # 3. Mostrar el Login (Corregido para versión moderna)
    authenticator.login(location='main')
    
    # 4. Revisar si el usuario entró
    auth_status = st.session_state.get("authentication_status")
    if auth_status is False:
        st.error('Usuario o contraseña incorrectos')
    elif auth_status is None:
        st.warning('Por favor ingresa tu usuario y contraseña')
    elif auth_status:
        # Pantalla de Bienvenida
        st.title(f'Bienvenido {st.session_state["name"]}')
        authenticator.logout('Cerrar sesión', 'main', key='unique_key')
        
        st.success("¡Has accedido correctamente!")
        st.info("Aquí puedes continuar con el desarrollo de tu programa de inventarios.")

# El interruptor principal
if __name__ == "__main__":
    main()