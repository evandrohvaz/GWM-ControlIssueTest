import streamlit as st
import pandas as pd
from auth import (
    is_logged_in, 
    is_admin, 
    get_current_user, 
    logout, 
    login_page,
    load_users,
    create_user,
    delete_user,
    change_password,
    init_users_file
)

def admin_page():
    """Página de administração para gerenciar usuários."""
    # Verifica se o usuário está logado
    if not is_logged_in():
        login_page()
        return
    
    # Verifica se é admin
    if not is_admin():
        st.error("❌ Acesso negado. Apenas administradores podem acessar esta página.")
        st.info("🔙 Execute 'streamlit run app_reparo.py' para voltar à página principal.")
        return
    
    st.set_page_config(
        page_title="Admin - Gerenciar Usuários",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    current_user = get_current_user()
    
    st.title("⚙️ Administração - Gerenciar Usuários")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("👤 Usuário")
        st.info(f"**Logado como:**\n{current_user['nome'] if current_user else ''}")
        if st.button("🚪 Sair", use_container_width=True):
            logout()
            st.rerun()
        
        st.markdown("---")
        st.info("💡 **Voltar:** Execute 'streamlit run app_reparo.py' para voltar ao sistema principal.")
    
    # Inicializa arquivo de usuários
    init_users_file()
    
    # Tabs para diferentes operações
    tab1, tab2, tab3 = st.tabs(["➕ Cadastrar Usuário", "👥 Listar Usuários", "🔑 Alterar Senha"])
    
    # --- TAB 1: CADASTRAR USUÁRIO ---
    with tab1:
        st.header("Cadastrar Novo Usuário")
        
        with st.form("form_cadastrar_usuario", clear_on_submit=True):
            novo_username = st.text_input("Nome de Usuário (Login)", help="Nome que será usado para fazer login.")
            novo_nome = st.text_input("Nome Completo", help="Nome completo do operador que aparecerá no sistema.")
            nova_senha = st.text_input("Senha", type="password", help="Senha para acesso ao sistema.")
            confirmar_senha = st.text_input("Confirmar Senha", type="password")
            is_admin_user = st.checkbox("É Administrador?", help="Marque se este usuário terá permissões de administrador.")
            
            submitted = st.form_submit_button("✅ Cadastrar Usuário", use_container_width=True, type="primary")
            
            if submitted:
                if not novo_username:
                    st.error("❌ Nome de usuário é obrigatório.")
                elif not novo_nome:
                    st.error("❌ Nome completo é obrigatório.")
                elif not nova_senha:
                    st.error("❌ Senha é obrigatória.")
                elif nova_senha != confirmar_senha:
                    st.error("❌ As senhas não coincidem.")
                elif len(nova_senha) < 4:
                    st.error("❌ A senha deve ter pelo menos 4 caracteres.")
                else:
                    success, message = create_user(novo_username, nova_senha, novo_nome, is_admin_user)
                    if success:
                        st.success(f"✅ {message}")
                    else:
                        st.error(f"❌ {message}")
    
    # --- TAB 2: LISTAR USUÁRIOS ---
    with tab2:
        st.header("Lista de Usuários Cadastrados")
        
        users = load_users()
        
        if users:
            # Cria DataFrame para exibição
            users_data = []
            for username, user_data in users.items():
                users_data.append({
                    'Usuário': username,
                    'Nome': user_data.get('nome', 'N/A'),
                    'Admin': 'Sim' if user_data.get('is_admin', False) else 'Não'
                })
            
            df_users = pd.DataFrame(users_data)
            st.dataframe(df_users, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("Deletar Usuário")
            
            with st.form("form_deletar_usuario"):
                username_to_delete = st.selectbox(
                    "Selecione o usuário para deletar",
                    options=[u for u in users.keys() if u != 'admin'],  # Não permite deletar admin
                    help="⚠️ Esta ação não pode ser desfeita!"
                )
                
                submitted_delete = st.form_submit_button("🗑️ Deletar Usuário", use_container_width=True, type="secondary")
                
                if submitted_delete:
                    if username_to_delete:
                        success, message = delete_user(username_to_delete)
                        if success:
                            st.success(f"✅ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
        else:
            st.info("Nenhum usuário cadastrado.")
    
    # --- TAB 3: ALTERAR SENHA ---
    with tab3:
        st.header("Alterar Senha")
        
        users = load_users()
        
        with st.form("form_alterar_senha", clear_on_submit=True):
            username_change = st.selectbox(
                "Selecione o usuário",
                options=list(users.keys()),
                help="Selecione o usuário para alterar a senha."
            )
            
            # Se for outro usuário (não o admin logado), precisa da senha atual
            current_username = st.session_state.get('username', '')
            if username_change != current_username:
                st.warning("⚠️ Para alterar a senha de outro usuário, você precisa da senha atual dele.")
                senha_atual = st.text_input("Senha Atual do Usuário", type="password")
            else:
                senha_atual = st.text_input("Senha Atual", type="password")
            
            nova_senha_change = st.text_input("Nova Senha", type="password")
            confirmar_senha_change = st.text_input("Confirmar Nova Senha", type="password")
            
            submitted_change = st.form_submit_button("🔑 Alterar Senha", use_container_width=True, type="primary")
            
            if submitted_change:
                if not senha_atual:
                    st.error("❌ Senha atual é obrigatória.")
                elif not nova_senha_change:
                    st.error("❌ Nova senha é obrigatória.")
                elif nova_senha_change != confirmar_senha_change:
                    st.error("❌ As senhas não coincidem.")
                elif len(nova_senha_change) < 4:
                    st.error("❌ A senha deve ter pelo menos 4 caracteres.")
                else:
                    # Para alterar senha de outro usuário, precisamos verificar a senha atual
                    from auth import verify_password, hash_password, save_users
                    users = load_users()
                    if username_change in users:
                        if verify_password(senha_atual, users[username_change]['password_hash']):
                            users[username_change]['password_hash'] = hash_password(nova_senha_change)
                            save_users(users)
                            st.success("✅ Senha alterada com sucesso!")
                        else:
                            st.error("❌ Senha atual incorreta.")
                    else:
                        st.error("❌ Usuário não encontrado.")

if __name__ == "__main__":
    admin_page()

