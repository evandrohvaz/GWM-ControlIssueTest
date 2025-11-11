import streamlit as st
import json
import hashlib
import os

# Arquivo para armazenar usuários
USERS_FILE = 'users.json'
ADMIN_USERNAME = 'admin'  # Usuário administrador padrão
ADMIN_PASSWORD_HASH = hashlib.sha256('admin123'.encode()).hexdigest()  # Senha padrão: admin123

def init_users_file():
    """Inicializa o arquivo de usuários com o admin padrão se não existir."""
    if not os.path.exists(USERS_FILE):
        users = {
            ADMIN_USERNAME: {
                'password_hash': ADMIN_PASSWORD_HASH,
                'nome': 'Administrador',
                'is_admin': True
            }
        }
        save_users(users)
    return load_users()

def load_users():
    """Carrega os usuários do arquivo JSON."""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    """Salva os usuários no arquivo JSON."""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def hash_password(password):
    """Gera o hash da senha."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    """Verifica se a senha está correta."""
    return hash_password(password) == password_hash

def authenticate(username, password):
    """Autentica um usuário."""
    users = load_users()
    if username in users:
        if verify_password(password, users[username]['password_hash']):
            return True, users[username]
    return False, None

def create_user(username, password, nome, is_admin=False):
    """Cria um novo usuário."""
    users = load_users()
    if username in users:
        return False, "Usuário já existe."
    
    users[username] = {
        'password_hash': hash_password(password),
        'nome': nome,
        'is_admin': is_admin
    }
    save_users(users)
    return True, "Usuário criado com sucesso!"

def delete_user(username):
    """Deleta um usuário."""
    users = load_users()
    if username == ADMIN_USERNAME:
        return False, "Não é possível deletar o usuário administrador."
    if username in users:
        del users[username]
        save_users(users)
        return True, "Usuário deletado com sucesso!"
    return False, "Usuário não encontrado."

def change_password(username, old_password, new_password):
    """Altera a senha de um usuário."""
    users = load_users()
    if username in users:
        if verify_password(old_password, users[username]['password_hash']):
            users[username]['password_hash'] = hash_password(new_password)
            save_users(users)
            return True, "Senha alterada com sucesso!"
        return False, "Senha atual incorreta."
    return False, "Usuário não encontrado."

def is_logged_in():
    """Verifica se há um usuário logado."""
    return 'logged_in' in st.session_state and st.session_state['logged_in']

def get_current_user():
    """Retorna o usuário atual logado."""
    if is_logged_in():
        return st.session_state.get('user', None)
    return None

def is_admin():
    """Verifica se o usuário logado é admin."""
    user = get_current_user()
    return user and user.get('is_admin', False)

def logout():
    """Faz logout do usuário."""
    if 'logged_in' in st.session_state:
        del st.session_state['logged_in']
    if 'user' in st.session_state:
        del st.session_state['user']
    if 'username' in st.session_state:
        del st.session_state['username']

def login_page():
    """Exibe a página de login."""
    st.set_page_config(
        page_title="Login - Sistema de Reparos",
        layout="centered",
        initial_sidebar_state="collapsed"
    )
    
    st.title("🔐 Login - Sistema de Reparos")
    st.markdown("---")
    
    # Inicializa arquivo de usuários
    init_users_file()
    
    with st.form("login_form"):
        username = st.text_input("Usuário", key="login_username")
        password = st.text_input("Senha", type="password", key="login_password")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")
        
        if submitted:
            if username and password:
                success, user = authenticate(username, password)
                if success:
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = user
                    st.session_state['username'] = username
                    st.success(f"✅ Bem-vindo, {user['nome']}!")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos.")
            else:
                st.warning("⚠️ Preencha usuário e senha.")
    
    st.markdown("---")
