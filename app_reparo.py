import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from uuid import uuid4
from auth import is_logged_in, get_current_user, logout, login_page

# --- 1. CONFIGURAÇÕES E CONSTANTES ---
DB_NAME = 'reparos.db'

# --- 2. FUNÇÕES DO BANCO DE DADOS (SQLite) ---
def init_db():
    """Cria a tabela de reparos se ela não existir."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id TEXT PRIMARY KEY,
            vin TEXT NOT NULL,
            operador_id TEXT,
            tipo_retrabalho TEXT,
            shop TEXT,
            hora_inicio TEXT,
            hora_fim TEXT
        )
    """)
    # Adiciona as novas colunas se não existirem (para compatibilidade com banco existente)
    try:
        c.execute("ALTER TABLE registros ADD COLUMN tipo_retrabalho TEXT")
    except sqlite3.OperationalError:
        pass  # Coluna já existe
    try:
        c.execute("ALTER TABLE registros ADD COLUMN shop TEXT")
    except sqlite3.OperationalError:
        pass  # Coluna já existe
    conn.commit()
    conn.close()

def validar_vin(vin):
    """Valida se o VIN não está vazio."""
    if not vin:
        return False, "VIN não pode estar vazio."
    vin_limpo = vin.upper().strip()
    return True, vin_limpo

def verificar_reparo_aberto(vin):
    """Verifica se existe reparo em aberto para o VIN."""
    init_db()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT id, operador_id, hora_inicio FROM registros 
        WHERE vin = ? AND hora_fim IS NULL 
        ORDER BY hora_inicio DESC 
        LIMIT 1
    """, (vin.upper(),))
    resultado = c.fetchone()
    conn.close()
    return resultado

def iniciar_reparo(vin, operador_id, tipo_retrabalho=None, shop=None):
    """Registra o início do reparo no banco de dados."""
    # Valida VIN
    vin_valido, vin_formatado = validar_vin(vin)
    if not vin_valido:
        return False, vin_formatado
    
    # Verifica se já existe reparo em aberto
    reparo_aberto = verificar_reparo_aberto(vin_formatado)
    if reparo_aberto:
        hora_inicio_existente = datetime.strptime(reparo_aberto[2], '%Y-%m-%d %H:%M:%S')
        tempo_decorrido = datetime.now() - hora_inicio_existente
        return False, f"Já existe um reparo em aberto para este VIN iniciado há {int(tempo_decorrido.total_seconds() / 60)} minutos. Finalize o reparo anterior primeiro."
    
    init_db()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    reparo_id = str(uuid4())
    hora_inicio = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        c.execute("INSERT INTO registros (id, vin, operador_id, tipo_retrabalho, shop, hora_inicio) VALUES (?, ?, ?, ?, ?, ?)",
                  (reparo_id, vin_formatado, operador_id.strip().upper(), tipo_retrabalho.strip() if tipo_retrabalho else None, shop if shop else None, hora_inicio))
        conn.commit()
        return True, reparo_id
    except sqlite3.Error as e:
        return False, f"Erro ao iniciar: {e}"
    finally:
        conn.close()

def finalizar_reparo(vin):
    """Registra a hora de fim para o último reparo INCOMPLETO desse VIN."""
    # Valida VIN
    vin_valido, vin_formatado = validar_vin(vin)
    if not vin_valido:
        return False, vin_formatado, None, None
    
    init_db()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    hora_fim = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Encontra o reparo mais recente para este VIN que ainda não foi finalizado
    c.execute("""
        SELECT id, hora_inicio, operador_id FROM registros 
        WHERE vin = ? AND hora_fim IS NULL 
        ORDER BY hora_inicio DESC 
        LIMIT 1
    """, (vin_formatado,))
    
    reparo_incompleto = c.fetchone()
    
    if reparo_incompleto:
        reparo_id = reparo_incompleto[0]
        hora_inicio = datetime.strptime(reparo_incompleto[1], '%Y-%m-%d %H:%M:%S')
        operador_id = reparo_incompleto[2]
        hora_fim_dt = datetime.strptime(hora_fim, '%Y-%m-%d %H:%M:%S')
        duracao = hora_fim_dt - hora_inicio
        
        c.execute("UPDATE registros SET hora_fim = ? WHERE id = ?", (hora_fim, reparo_id))
        conn.commit()
        conn.close()
        return True, reparo_id, duracao, operador_id
    else:
        conn.close()
        return False, "Nenhum reparo em aberto encontrado para este VIN.", None, None

def get_registros(filtro_operador=None, filtro_vin=None, filtro_data_inicio=None, filtro_data_fim=None, apenas_completos=False):
    """Retorna todos os registros para visualização e cálculo."""
    init_db()
    conn = sqlite3.connect(DB_NAME)
    
    query = "SELECT id, vin, operador_id, tipo_retrabalho, shop, hora_inicio, hora_fim FROM registros WHERE 1=1"
    params = []
    
    if filtro_operador:
        query += " AND operador_id = ?"
        params.append(filtro_operador.upper())
    if filtro_vin:
        query += " AND vin = ?"
        params.append(filtro_vin.upper())
    if filtro_data_inicio:
        query += " AND DATE(hora_inicio) >= ?"
        params.append(filtro_data_inicio)
    if filtro_data_fim:
        query += " AND DATE(hora_inicio) <= ?"
        params.append(filtro_data_fim)
    if apenas_completos:
        query += " AND hora_fim IS NOT NULL"
    
    query += " ORDER BY hora_inicio DESC"
    
    df = pd.read_sql_query(query, conn, params=params if params else None)
    conn.close()
    
    if df.empty:
        return df
    
    # Processamento para cálculo do tempo
    df['hora_inicio'] = pd.to_datetime(df['hora_inicio'])
    df['hora_fim'] = pd.to_datetime(df['hora_fim'], errors='coerce')
    df['duracao'] = df['hora_fim'] - df['hora_inicio']
    df['duracao_minutos'] = df['duracao'].dt.total_seconds() / 60
    df['duracao_horas'] = df['duracao_minutos'] / 60
    
    # Formatação de data
    df['data'] = df['hora_inicio'].dt.date
    
    # Seleciona e renomeia as colunas para o display
    colunas_display = {
        'vin': 'VIN',
        'operador_id': 'Operador',
        'tipo_retrabalho': 'Tipo Retrabalho',
        'shop': 'Shop',
        'hora_inicio': 'Início',
        'hora_fim': 'Fim',
        'duracao_minutos': 'Duração (min)',
        'duracao_horas': 'Duração (h)',
        'data': 'Data'
    }
    
    df_display = df.rename(columns=colunas_display)
    
    return df_display

def get_reparos_abertos(filtro_operador=None):
    """Retorna todos os reparos que ainda não foram finalizados."""
    init_db()
    conn = sqlite3.connect(DB_NAME)
    
    query = """
        SELECT vin, operador_id, tipo_retrabalho, shop, hora_inicio 
        FROM registros 
        WHERE hora_fim IS NULL
    """
    params = []
    
    if filtro_operador:
        query += " AND operador_id = ?"
        params.append(filtro_operador)
    
    query += " ORDER BY hora_inicio DESC"
    
    df = pd.read_sql_query(query, conn, params=params if params else None)
    conn.close()
    
    if df.empty:
        return df
    
    df['hora_inicio'] = pd.to_datetime(df['hora_inicio'])
    df['tempo_decorrido'] = datetime.now() - df['hora_inicio']
    df['tempo_decorrido_min'] = df['tempo_decorrido'].dt.total_seconds() / 60
    
    return df.rename(columns={
        'vin': 'VIN',
        'operador_id': 'Operador',
        'tipo_retrabalho': 'Tipo Retrabalho',
        'shop': 'Shop',
        'hora_inicio': 'Início',
        'tempo_decorrido_min': 'Tempo Decorrido (min)'
    })


# --- 3. INTERFACE DO STREAMLIT ---
def app():
    # Verifica se o usuário está logado
    if not is_logged_in():
        login_page()
        return
    
    st.set_page_config(
        page_title="Registro de Tempo de Reparo", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Obtém o usuário logado
    current_user = get_current_user()
    user_nome = current_user['nome'] if current_user else ''
    
    # Sidebar com informações
    with st.sidebar:
        st.header("👤 Usuário")
        st.info(f"**Logado como:**\n{user_nome}")
        if st.button("🚪 Sair", use_container_width=True):
            logout()
            st.rerun()

        st.markdown("---")
        st.header("📋 Sobre")
        st.info("""
        **Sistema de Registro de Tempo de Reparos**
        
        - Inicie o reparo apontando o VIN
        - Finalize apontando o mesmo VIN
        - Visualize estatísticas e relatórios
        """)
    
    st.title("⏱️ Registro de Reparos")
    st.subheader("Aponte o VIN para iniciar ou finalizar o serviço.")

    # Verifica se é admin para definir quais tabs mostrar
    from auth import is_admin
    user_is_admin = is_admin()
    
    # Tabs organizadas - diferentes para admin e usuário normal
    if user_is_admin:
        # Admin vê todas as abas
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "▶️ Iniciar Reparo", 
            "🛑 Finalizar Reparo", 
            "📊 Visualizar Dados",
            "⏳ Reparos em Aberto",
            "📈 Relatórios"
        ])
    else:
        # Usuário normal vê apenas as abas permitidas
        tab1, tab2, tab4 = st.tabs([
            "▶️ Iniciar Reparo", 
            "🛑 Finalizar Reparo", 
            "⏳ Reparos em Aberto"
        ])
        # Cria tabs vazios para manter compatibilidade com o código
        tab3 = None
        tab5 = None
    
    # --- ABA 1: INICIAR REPARO ---
    with tab1:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header("Início do Serviço")
            
            # Usa st.form para limpar campos automaticamente após submit
            with st.form("form_iniciar_reparo", clear_on_submit=True):
                # Campo de operador preenchido automaticamente com o nome do usuário logado
                # Usa st.text_input com disabled=False mas sempre preenche com o nome do usuário
                operador_id_display = st.text_input(
                    "ID do Operador (Obrigatório)", 
                    value=user_nome,
                    disabled=True,
                    key="op_id_start", 
                    help="ID do operador (preenchido automaticamente com seu nome de usuário)."
                )
                # Variável que será usada sempre será o nome do usuário
                operador_id = user_nome
                vin_start = st.text_input(
                    "VIN do Carro (Obrigatório)", 
                    key="vin_start", 
                    help="Digite ou escaneie o VIN do carro.", 
                    placeholder="Ex: 3FA2P00000X123456"
                )
                tipo_retrabalho = st.text_input(
                    "Tipo de Retrabalho (Opcional)",
                    key="tipo_retrabalho",
                    help="Descreva o tipo de retrabalho que está sendo realizado (opcional)."
                )
                shop = st.selectbox(
                    "Shop (Obrigatório)",
                    options=["BS", "PS", "GA"],
                    key="shop",
                    help="Selecione o shop onde o reparo está sendo realizado."
                )
                
                submitted = st.form_submit_button("🔴 INICIAR REPARO AGORA", use_container_width=True, type="primary")
                
                if submitted:
                    # Valida campos obrigatórios
                    if not vin_start:
                        st.error("❌ **Erro:** VIN é obrigatório.")
                    elif not user_nome:
                        st.error("❌ **Erro:** Usuário não identificado. Faça login novamente.")
                    elif not shop:
                        st.error("❌ **Erro:** Shop é obrigatório.")
                    else:
                        vin_start_upper = vin_start.upper().strip()
                        # Valida VIN (apenas verifica se não está vazio)
                        vin_valido, msg_validacao = validar_vin(vin_start_upper)
                        if not vin_valido:
                            st.error(f"❌ **Erro de validação:**\n\n{msg_validacao}")
                        else:
                            # Sempre usa o nome do usuário logado como operador_id
                            sucesso, msg = iniciar_reparo(vin_start_upper, user_nome, tipo_retrabalho if tipo_retrabalho else None, shop)
                            if sucesso:
                                if user_is_admin:
                                    st.success("✅ **Reparo iniciado com sucesso!**")
                                else:
                                    st.success(f"✅ **Reparo iniciado com sucesso!**\n\n- VIN: **{vin_start_upper}**\n- Operador: **{user_nome}**\n- Tipo Retrabalho: **{tipo_retrabalho if tipo_retrabalho else 'N/A'}**\n- Shop: **{shop}**\n- Horário: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**")
                            else:
                                st.error(f"❌ **Falha ao iniciar o reparo:**\n\n{msg}")
            
            # Validação visual do VIN apenas para usuários normais (admin não precisa)
            if not user_is_admin:
                vin_start_atual = st.session_state.get('vin_start', '')
                if vin_start_atual:
                    vin_start_upper = vin_start_atual.upper().strip()
                    vin_valido, msg_validacao = validar_vin(vin_start_upper)
                    if not vin_valido:
                        st.error(f"⚠️ {msg_validacao}")
                    else:
                        # Verifica se já existe reparo em aberto
                        reparo_aberto = verificar_reparo_aberto(vin_start_upper)
                        if reparo_aberto:
                            hora_inicio_existente = datetime.strptime(reparo_aberto[2], '%Y-%m-%d %H:%M:%S')
                            tempo_decorrido = datetime.now() - hora_inicio_existente
                            st.warning(f"⚠️ Já existe um reparo em aberto para este VIN iniciado há {int(tempo_decorrido.total_seconds() / 60)} minutos.")
        
        with col2:
            st.markdown("### ℹ️ Informações")
            if user_is_admin:
                st.info("""
                **Como usar:**
                1. Digite ou escaneie o VIN (obrigatório)
                2. Selecione o shop - BS, PS ou GA (obrigatório)
                3. Informe o tipo de retrabalho (opcional)
                4. Clique em "INICIAR REPARO"
                
                Os campos serão limpos automaticamente após o registro.
                """)
            else:
                st.info("""
                **Como usar:**
                1. Digite o ID do operador (obrigatório)
                2. Digite ou escaneie o VIN (obrigatório)
                3. Selecione o shop - BS, PS ou GA (obrigatório)
                4. Informe o tipo de retrabalho (opcional)
                5. Clique em "INICIAR REPARO"
                
                Os campos serão limpos automaticamente após o registro.
                """)

    # --- ABA 2: FINALIZAR REPARO ---
    with tab2:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header("Fim do Serviço")
            
            # Usa st.form para limpar campo automaticamente após submit
            with st.form("form_finalizar_reparo", clear_on_submit=True):
                vin_end = st.text_input(
                    "VIN do Carro (Obrigatório)", 
                    key="vin_end", 
                    help="Digite ou escaneie o mesmo VIN usado para iniciar o reparo.", 
                    placeholder="Ex: 3FA2P00000X123456"
                )
                
                submitted_finalizar = st.form_submit_button("🟢 FINALIZAR REPARO AGORA", use_container_width=True, type="secondary")
                
                if submitted_finalizar:
                    if vin_end:
                        vin_end_upper = vin_end.upper().strip()
                        sucesso, msg, duracao, operador = finalizar_reparo(vin_end_upper)
                        if sucesso:
                            minutos = int(duracao.total_seconds() / 60)
                            horas = minutos / 60
                            
                            st.balloons()
                            st.success(f"🎉 **Reparo finalizado com sucesso!**")
                            
                            # Mostra informações detalhadas apenas para usuários normais
                            if not user_is_admin:
                                col_info1, col_info2 = st.columns(2)
                                with col_info1:
                                    st.metric("⏱️ Tempo Total", f"{minutos} min", f"{horas:.2f} horas")
                                with col_info2:
                                    st.metric("👤 Operador", operador)
                                
                                st.info(f"📋 **Detalhes:**\n- VIN: **{vin_end_upper}**\n- Finalizado em: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**")
                        else:
                            st.warning(f"⚠️ **Atenção:** {msg}")
                    else:
                        st.warning("⚠️ Preencha o VIN para finalizar.")
            
            # Mostra informações do reparo em aberto apenas para usuários normais (admin não precisa)
            if not user_is_admin:
                vin_end_atual = st.session_state.get('vin_end', '')
                if vin_end_atual:
                    vin_end_upper = vin_end_atual.upper().strip()
                    reparo_aberto = verificar_reparo_aberto(vin_end_upper)
                    if reparo_aberto:
                        hora_inicio_existente = datetime.strptime(reparo_aberto[2], '%Y-%m-%d %H:%M:%S')
                        tempo_decorrido = datetime.now() - hora_inicio_existente
                        minutos = int(tempo_decorrido.total_seconds() / 60)
                        horas = minutos // 60
                        min_restantes = minutos % 60
                        st.info(f"📋 **Reparo encontrado:**\n- Operador: **{reparo_aberto[1]}**\n- Iniciado: **{hora_inicio_existente.strftime('%d/%m/%Y %H:%M:%S')}**\n- Tempo decorrido: **{horas}h {min_restantes}min**")
                    else:
                        st.warning("⚠️ Nenhum reparo em aberto encontrado para este VIN.")
        
        with col2:
            st.markdown("### ℹ️ Informações")
            if user_is_admin:
                st.info("""
                **Ao finalizar:**
                - O reparo será registrado
                - O campo será limpo automaticamente
                """)
            else:
                st.info("""
                **Ao finalizar:**
                - O tempo total será calculado
                - Os dados estarão disponíveis nos relatórios
                - O campo será limpo automaticamente
                """)

    # --- ABA 3: VISUALIZAR DADOS (APENAS ADMIN) ---
    if user_is_admin and tab3:
        with tab3:
            st.header("Dados de Reparo Registrados")
            
            # Filtros
            col_filtro1, col_filtro2, col_filtro3, col_filtro4 = st.columns(4)
            with col_filtro1:
                filtro_operador = st.text_input("Filtrar por Operador", key="filtro_op", placeholder="ID do operador")
            with col_filtro2:
                filtro_vin = st.text_input("Filtrar por VIN", key="filtro_vin", placeholder="VIN")
            with col_filtro3:
                filtro_data_inicio = st.date_input("Data Início", key="filtro_dt_inicio", value=None)
            with col_filtro4:
                filtro_data_fim = st.date_input("Data Fim", key="filtro_dt_fim", value=None)
            
            apenas_completos = st.checkbox("Mostrar apenas reparos finalizados", value=True, key="check_completos")
            
            df_registros = get_registros(
                filtro_operador=filtro_operador if filtro_operador else None,
                filtro_vin=filtro_vin.upper() if filtro_vin else None,
                filtro_data_inicio=filtro_data_inicio.strftime('%Y-%m-%d') if filtro_data_inicio else None,
                filtro_data_fim=filtro_data_fim.strftime('%Y-%m-%d') if filtro_data_fim else None,
                apenas_completos=apenas_completos
            )
            
            if not df_registros.empty:
                # Seleciona colunas para exibição
                colunas_exibir = ['VIN', 'Operador', 'Tipo Retrabalho', 'Shop', 'Data', 'Início', 'Fim', 'Duração (min)']
                # Remove colunas que não existem no dataframe
                colunas_exibir = [col for col in colunas_exibir if col in df_registros.columns]
                df_exibir = df_registros[colunas_exibir]
                st.dataframe(df_exibir, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # Métricas
                reparos_completos = df_registros['Duração (min)'].dropna()
                
                if not reparos_completos.empty:
                    col_met1, col_met2, col_met3 = st.columns(3)
                    
                    with col_met1:
                        tempo_medio = reparos_completos.mean()
                        st.metric("⏱️ Tempo Médio (MTTR)", f"{tempo_medio:.1f} min")
                    
                    with col_met2:
                        tempo_total = reparos_completos.sum()
                        st.metric("⏱️ Tempo Total", f"{tempo_total:.1f} min", f"{tempo_total/60:.1f} h")
                    
                    with col_met3:
                        total_reparos = len(reparos_completos)
                        st.metric("📊 Total de Reparos", total_reparos)
                    
                    # Exportar CSV
                    st.markdown("---")
                    csv = df_exibir.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 Download dos Dados (CSV)",
                        data=csv,
                        file_name=f'registros_reparos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                        mime='text/csv',
                        use_container_width=True
                    )
                else:
                    st.info("Nenhum reparo finalizado encontrado com os filtros aplicados.")
            else:
                st.info("Nenhum registro encontrado com os filtros aplicados.")
    
    # --- ABA 4: REPAROS EM ABERTO ---
    with tab4:
        st.header("Reparos em Andamento")
        
        # Se for admin, mostra todos os reparos em aberto
        # Se for usuário normal, mostra apenas os reparos do operador logado
        if user_is_admin:
            st.info("Lista de todos os reparos que foram iniciados mas ainda não foram finalizados.")
            df_abertos = get_reparos_abertos()
        else:
            st.info(f"Lista dos seus reparos em andamento.")
            # Usa o nome do usuário em maiúsculas para corresponder ao banco de dados
            df_abertos = get_reparos_abertos(filtro_operador=user_nome.upper() if user_nome else None)
        
        if not df_abertos.empty:
            # Seleciona apenas colunas relevantes
            colunas_abertos = ['VIN', 'Operador', 'Tipo Retrabalho', 'Shop', 'Início', 'Tempo Decorrido (min)']
            # Remove colunas que não existem no dataframe
            colunas_abertos = [col for col in colunas_abertos if col in df_abertos.columns]
            df_abertos_display = df_abertos[colunas_abertos].copy()
            if 'Tempo Decorrido (min)' in df_abertos_display.columns:
                df_abertos_display['Tempo Decorrido (min)'] = df_abertos_display['Tempo Decorrido (min)'].round(1)
            
            st.dataframe(df_abertos_display, use_container_width=True, hide_index=True)
            
            # Estatísticas apenas para usuários normais (admin não vê métricas aqui)
            if not user_is_admin:
                col_stat1, col_stat2 = st.columns(2)
                with col_stat1:
                    st.metric("📊 Total de Reparos em Aberto", len(df_abertos))
                with col_stat2:
                    tempo_total_aberto = df_abertos['Tempo Decorrido (min)'].sum()
                    st.metric("⏱️ Tempo Total em Aberto", f"{tempo_total_aberto:.1f} min", f"{tempo_total_aberto/60:.1f} h")
        else:
            if user_is_admin:
                st.success("✅ Nenhum reparo em aberto no momento!")
            else:
                st.success("✅ Você não possui reparos em aberto no momento!")
    
    # --- ABA 5: RELATÓRIOS (APENAS ADMIN) ---
    if user_is_admin and tab5:
        with tab5:
            st.header("Relatórios e Análises")
            
            df_registros = get_registros(apenas_completos=True)
            
            if df_registros.empty:
                st.info("Nenhum reparo finalizado ainda para gerar relatórios.")
            else:
                # Gráficos
                col_graf1, col_graf2 = st.columns(2)
                
                with col_graf1:
                    st.subheader("📊 Reparos por Operador")
                    reparos_por_operador = df_registros.groupby('Operador').size().sort_values(ascending=False)
                    if not reparos_por_operador.empty:
                        st.bar_chart(reparos_por_operador)
                
                with col_graf2:
                    st.subheader("⏱️ Tempo Médio por Operador")
                    tempo_medio_operador = df_registros.groupby('Operador')['Duração (min)'].mean().sort_values(ascending=False)
                    if not tempo_medio_operador.empty:
                        st.bar_chart(tempo_medio_operador)
                
                st.markdown("---")
                
                # Gráfico de linha - Reparos ao longo do tempo
                st.subheader("📈 Reparos ao Longo do Tempo")
                reparos_por_data = df_registros.groupby('Data').size()
                if not reparos_por_data.empty:
                    st.line_chart(reparos_por_data)
                
                st.markdown("---")
                
                # Tabela de resumo por operador
                st.subheader("📋 Resumo por Operador")
                resumo_operador = df_registros.groupby('Operador').agg({
                    'Duração (min)': ['count', 'mean', 'sum'],
                    'VIN': 'count'
                }).round(2)
                
                resumo_operador.columns = ['Total Reparos', 'Tempo Médio (min)', 'Tempo Total (min)', 'Total VINs']
                resumo_operador['Tempo Total (h)'] = (resumo_operador['Tempo Total (min)'] / 60).round(2)
                
                st.dataframe(resumo_operador, use_container_width=True)
                
                # Histórico por VIN
                st.markdown("---")
                st.subheader("🔍 Histórico por VIN")
                vin_busca = st.text_input("Digite o VIN para ver o histórico", key="hist_vin", placeholder="VIN")
                
                if vin_busca:
                    vin_busca = vin_busca.upper().strip()
                    df_vin = get_registros(filtro_vin=vin_busca, apenas_completos=False)
                    if not df_vin.empty:
                        colunas_vin = ['Operador', 'Tipo Retrabalho', 'Shop', 'Data', 'Início', 'Fim', 'Duração (min)']
                        colunas_vin = [col for col in colunas_vin if col in df_vin.columns]
                        st.dataframe(df_vin[colunas_vin], use_container_width=True, hide_index=True)
                        
                        # Estatísticas do VIN
                        col_vin1, col_vin2 = st.columns(2)
                        with col_vin1:
                            st.metric("Total de Reparos", len(df_vin))
                        with col_vin2:
                            tempo_total_vin = df_vin['Duração (min)'].dropna().sum()
                            st.metric("Tempo Total", f"{tempo_total_vin:.1f} min")
                    else:
                        st.warning(f"Nenhum registro encontrado para o VIN {vin_busca}.")
             
if __name__ == "__main__":
    init_db()  # Garante que o banco de dados seja inicializado ao rodar o script
    app()