import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui_para_sessoes'

# ==========================================
# CONEXÃO COM BANCO DE DADOS
# ==========================================
def conectar():
    try:
        conexao = mysql.connector.connect(
            host='localhost',
            user='root',
            password='69941777',
            database='farmacia_db'
        )
        return conexao
    except Error as e:
        print("Erro ao conectar ao Banco de Dados:", e)
        return None

# ==========================================
# DECORATOR DE AUTENTICAÇÃO (LOGIN)
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Faça login para acessar o sistema.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# 1. LOGIN & LOGOUT
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha = request.form.get('senha')
        
        conexao = conectar()
        if conexao:
            try:
                cursor = conexao.cursor(dictionary=True)
                cursor.execute("SELECT * FROM usuarios WHERE login = %s AND senha_hash = %s", (usuario, senha))
                user = cursor.fetchone()
                cursor.close()
                
                if user:
                    session['usuario_id'] = user['id_usuario']
                    session['usuario_nome'] = user['nome']
                    flash('Login realizado com sucesso!', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('Usuário ou senha incorretos.', 'danger')
            except Error as e:
                flash(f'Erro no banco de dados: {e}', 'danger')
            finally:
                conexao.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# ==========================================
# 2. DASHBOARD / HOME
# ==========================================
@app.route('/')
@app.route('/dashboard', endpoint='dashboard')
@login_required
def index():
    conexao = conectar()
    vendas_hoje = 0.0
    vendas_mes = 0.0
    total_clientes = 0
    estoque_baixo = 0
    ultimas_vendas = []

    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)

            cursor.execute("SELECT COALESCE(SUM(total), 0) AS total FROM vendas WHERE DATE(data_venda) = CURDATE() AND status = 'FINALIZADA'")
            res = cursor.fetchone()
            vendas_hoje = float(res['total']) if res else 0.0

            cursor.execute("SELECT COALESCE(SUM(total), 0) AS total FROM vendas WHERE MONTH(data_venda) = MONTH(CURDATE()) AND YEAR(data_venda) = YEAR(CURDATE()) AND status = 'FINALIZADA'")
            res = cursor.fetchone()
            vendas_mes = float(res['total']) if res else 0.0

            cursor.execute("SELECT COUNT(*) AS total FROM clientes")
            res = cursor.fetchone()
            total_clientes = res['total'] if res else 0

            cursor.execute("SELECT COUNT(*) AS total FROM lotes WHERE quantidade_atual <= 10")
            res = cursor.fetchone()
            estoque_baixo = res['total'] if res else 0

            sql_ultimas = """
                SELECT 
                    v.id_venda, 
                    v.data_venda, 
                    COALESCE(c.nome, 'Cliente Avulso') AS cliente, 
                    v.total 
                FROM vendas v 
                LEFT JOIN clientes c ON v.id_cliente = c.id_cliente 
                ORDER BY v.id_venda DESC LIMIT 5
            """
            cursor.execute(sql_ultimas)
            ultimas_vendas = cursor.fetchall()

            cursor.close()
        except Error as e:
            print("Erro no Dashboard:", e)
        finally:
            conexao.close()

    return render_template('index.html', 
                           vendas_hoje=vendas_hoje, 
                           vendas_mes=vendas_mes, 
                           total_clientes=total_clientes, 
                           estoque_baixo=estoque_baixo, 
                           ultimas_vendas=ultimas_vendas)

# ==========================================
# 3. VENDAS
# ==========================================
@app.route('/vendas', methods=['GET', 'POST'])
@login_required
def vendas():
    conexao = conectar()
    if request.method == 'POST':
        id_cliente = request.form.get('id_cliente') or None
        id_lote = request.form.get('id_lote')
        quantidade = int(request.form.get('quantidade', 1))

        if not id_lote:
            flash('Selecione um produto/lote válido!', 'warning')
            return redirect(url_for('vendas'))

        if conexao:
            try:
                cursor = conexao.cursor(dictionary=True)

                cursor.execute("""
                    SELECT l.id_lote, l.id_produto, l.quantidade_atual, p.preco_venda 
                    FROM lotes l 
                    JOIN produtos p ON l.id_produto = p.id_produto 
                    WHERE l.id_lote = %s
                """, (id_lote,))
                lote = cursor.fetchone()

                if not lote or lote['quantidade_atual'] < quantidade:
                    flash('Estoque insuficiente para este lote!', 'danger')
                    return redirect(url_for('vendas'))

                preco_unitario = float(lote['preco_venda'])
                subtotal = preco_unitario * quantidade
                total = subtotal

                cursor.execute("SELECT id_caixa FROM caixas LIMIT 1")
                caixa = cursor.fetchone()
                id_caixa = caixa['id_caixa'] if caixa else None

                sql_venda = """
                    INSERT INTO vendas (id_caixa, id_cliente, id_usuario, subtotal, desconto, total, status)
                    VALUES (%s, %s, %s, %s, 0.00, %s, 'FINALIZADA')
                """
                cursor.execute(sql_venda, (id_caixa, id_cliente, session.get('usuario_id'), subtotal, total))
                id_venda = cursor.lastrowid

                sql_item = """
                    INSERT INTO itens_venda (id_venda, id_produto, id_lote, quantidade, preco_unitario, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql_item, (id_venda, lote['id_produto'], id_lote, quantidade, preco_unitario, subtotal))

                nova_qtd = lote['quantidade_atual'] - quantidade
                cursor.execute("UPDATE lotes SET quantidade_atual = %s WHERE id_lote = %s", (nova_qtd, id_lote))

                conexao.commit()
                cursor.close()
                flash('Venda realizada com sucesso!', 'success')
            except Error as e:
                conexao.rollback()
                print("Erro ao processar venda:", e)
                flash(f'Erro ao realizar venda: {e}', 'danger')
            finally:
                conexao.close()
        return redirect(url_for('vendas'))

    clientes = []
    produtos_lotes = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT id_cliente, nome FROM clientes ORDER BY nome ASC")
            clientes = cursor.fetchall()

            sql_produtos = """
                SELECT 
                    l.id_lote,
                    p.nome AS produto,
                    l.numero_lote,
                    l.quantidade_atual,
                    p.preco_venda
                FROM lotes l
                JOIN produtos p ON l.id_produto = p.id_produto
                WHERE l.quantidade_atual > 0 AND p.ativo = TRUE
                ORDER BY p.nome ASC
            """
            cursor.execute(sql_produtos)
            produtos_lotes = cursor.fetchall()
            cursor.close()
        except Error as e:
            print("Erro ao carregar formulário de vendas:", e)
        finally:
            conexao.close()

    return render_template('vendas.html', clientes=clientes, produtos=produtos_lotes)

# ==========================================
# 4. CONTROLE DE ESTOQUE
# ==========================================
@app.route('/estoque')
@login_required
def estoque():
    conexao = conectar()
    produtos_estoque = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            sql = """
                SELECT 
                    p.id_produto,
                    p.nome AS produto,
                    c.nome AS categoria,
                    COALESCE(SUM(l.quantidade_atual), 0) AS total_estoque,
                    p.preco_venda
                FROM produtos p
                LEFT JOIN categorias c ON p.id_categoria = c.id_categoria
                LEFT JOIN lotes l ON p.id_produto = l.id_produto
                WHERE p.ativo = TRUE
                GROUP BY p.id_produto, p.nome, c.nome, p.preco_venda
                ORDER BY p.nome ASC
            """
            cursor.execute(sql)
            produtos_estoque = cursor.fetchall()
            cursor.close()
        except Error as erro:
            print("Erro ao carregar estoque:", erro)
        finally:
            conexao.close()

    return render_template('estoque.html', produtos=produtos_estoque)

# ==========================================
# 5. ENTRADA DE ESTOQUE
# ==========================================
@app.route('/entrada_estoque', methods=['GET', 'POST'])
@login_required
def entrada_estoque():
    conexao = conectar()
    if request.method == 'POST':
        id_produto = request.form.get('id_produto')
        id_fornecedor = request.form.get('id_fornecedor') or None
        numero_lote = request.form.get('numero_lote')
        data_validade = request.form.get('data_validade')
        quantidade = int(request.form.get('quantidade', 0))
        preco_custo = float(request.form.get('preco_custo', 0.0))

        if conexao:
            try:
                cursor = conexao.cursor()
                sql = """
                    INSERT INTO lotes (id_produto, id_fornecedor, numero_lote, data_fabricacao, data_validade, quantidade_inicial, quantidade_atual, preco_custo)
                    VALUES (%s, %s, %s, CURDATE(), %s, %s, %s, %s)
                """
                cursor.execute(sql, (id_produto, id_fornecedor, numero_lote, data_validade, quantidade, quantidade, preco_custo))
                conexao.commit()
                cursor.close()
                flash('Entrada de estoque cadastrada com sucesso!', 'success')
                return redirect(url_for('estoque'))
            except Error as e:
                conexao.rollback()
                flash(f'Erro ao cadastrar lote: {e}', 'danger')
            finally:
                conexao.close()

    produtos = []
    fornecedores = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT id_produto, nome FROM produtos WHERE ativo = TRUE ORDER BY nome ASC")
            produtos = cursor.fetchall()
            cursor.execute("SELECT id_fornecedor, razao_social AS nome FROM fornecedores ORDER BY razao_social ASC")
            fornecedores = cursor.fetchall()
            cursor.close()
        except Error as e:
            print("Erro entrada estoque GET:", e)
        finally:
            conexao.close()

    return render_template('entrada_estoque.html', produtos=produtos, fornecedores=fornecedores)

# ==========================================
# 6. SAÍDA DE ESTOQUE
# ==========================================
@app.route('/saida_estoque')
@login_required
def saida_estoque():
    return render_template('saida_estoque.html')

# ==========================================
# 7. RELATÓRIOS
# ==========================================
@app.route('/relatorios')
@login_required
def relatorios():
    conexao = conectar()
    vendas_hoje_total = 0.0
    total_vendas_mes = 0.0
    historico_vendas = []
    detalhes_lotes = []
    total_entradas = 0
    total_saidas = 0
    saldo_estoque = 0

    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            
            cursor.execute("SELECT COALESCE(SUM(total), 0) AS total FROM vendas WHERE DATE(data_venda) = CURDATE() AND status = 'FINALIZADA'")
            res_hoje = cursor.fetchone()
            vendas_hoje_total = float(res_hoje['total']) if res_hoje else 0.0

            cursor.execute("SELECT COALESCE(SUM(total), 0) AS total FROM vendas WHERE MONTH(data_venda) = MONTH(CURDATE()) AND YEAR(data_venda) = YEAR(CURDATE()) AND status = 'FINALIZADA'")
            res_mes = cursor.fetchone()
            total_vendas_mes = float(res_mes['total']) if res_mes else 0.0

            sql_historico = """
                SELECT 
                    v.id_venda,
                    v.data_venda,
                    COALESCE(c.nome, 'Cliente Avulso') AS cliente,
                    COALESCE(p.nome, 'Produto') AS produto,
                    COALESCE(iv.quantidade, 1) AS qtd,
                    v.total
                FROM vendas v
                LEFT JOIN clientes c ON v.id_cliente = c.id_cliente
                LEFT JOIN itens_venda iv ON v.id_venda = iv.id_venda
                LEFT JOIN produtos p ON iv.id_produto = p.id_produto
                ORDER BY v.id_venda DESC LIMIT 20
            """
            cursor.execute(sql_historico)
            historico_vendas = cursor.fetchall()

            sql_lotes = """
                SELECT 
                    p.nome AS produto,
                    l.numero_lote,
                    l.quantidade_inicial AS entradas,
                    (l.quantidade_inicial - l.quantidade_atual) AS saidas,
                    l.quantidade_atual AS saldo_atual,
                    l.data_validade
                FROM lotes l
                JOIN produtos p ON l.id_produto = p.id_produto
                ORDER BY p.nome ASC
            """
            cursor.execute(sql_lotes)
            detalhes_lotes = cursor.fetchall()

            cursor.execute("SELECT COALESCE(SUM(quantidade_inicial), 0) AS inicial, COALESCE(SUM(quantidade_atual), 0) AS atual FROM lotes")
            res_totais = cursor.fetchone()
            if res_totais:
                total_entradas = res_totais['inicial']
                saldo_estoque = res_totais['atual']
                total_saidas = total_entradas - saldo_estoque

            cursor.close()
        except Error as erro:
            print("Erro ao carregar relatorios:", erro)
        finally:
            conexao.close()

    return render_template(
        'relatorios.html', 
        vendas_hoje_total=vendas_hoje_total,
        total_vendas_mes=total_vendas_mes,
        vendas=historico_vendas,
        lotes=detalhes_lotes,
        total_entradas=total_entradas,
        total_saidas=total_saidas,
        saldo_estoque=saldo_estoque
    )

# ==========================================
# 8. MEDICAMENTOS / PRODUTOS
# ==========================================
@app.route('/medicamentos')
@login_required
def medicamentos():
    conexao = conectar()
    produtos = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            sql = """
                SELECT p.id_produto, p.nome, c.nome AS categoria, p.preco_custo, p.preco_venda, p.ativo
                FROM produtos p
                LEFT JOIN categorias c ON p.id_categoria = c.id_categoria
                ORDER BY p.nome ASC
            """
            cursor.execute(sql)
            produtos = cursor.fetchall()
            cursor.close()
        except Error as e:
            print("Erro ao carregar medicamentos:", e)
        finally:
            conexao.close()

    return render_template('medicamentos.html', produtos=produtos)

@app.route('/medicamentos/novo', methods=['GET', 'POST'])
@app.route('/cadastrar_medicamento', methods=['GET', 'POST'])
@app.route('/cadastrar_medicamentos', methods=['GET', 'POST'], endpoint='cadastrar_medicamentos')
@login_required
def cadastrar_medicamento():
    conexao = conectar()
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        id_categoria = request.form.get('id_categoria') or None
        preco_custo = request.form.get('preco_custo', 0.0)
        preco_venda = request.form.get('preco_venda', 0.0)

        if conexao:
            try:
                cursor = conexao.cursor()
                sql = """
                    INSERT INTO produtos (nome, id_categoria, preco_custo, preco_venda, ativo)
                    VALUES (%s, %s, %s, %s, TRUE)
                """
                cursor.execute(sql, (nome, id_categoria, preco_custo, preco_venda))
                conexao.commit()
                cursor.close()
                flash('Medicamento cadastrado com sucesso!', 'success')
                return redirect(url_for('medicamentos'))
            except Error as e:
                conexao.rollback()
                flash(f'Erro ao cadastrar medicamento: {e}', 'danger')
            finally:
                conexao.close()

    categorias = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT id_categoria, nome FROM categorias ORDER BY nome ASC")
            categorias = cursor.fetchall()
            cursor.close()
        except Error as e:
            print("Erro ao carregar categorias:", e)
        finally:
            conexao.close()

    try:
        return render_template('cadastrar_medicamentos.html', categorias=categorias)
    except Exception:
        return render_template('cadastrar_medicamento.html', categorias=categorias)

# --- EDITAR MEDICAMENTO ---
@app.route('/medicamentos/editar/<int:id_produto>', methods=['GET', 'POST'])
@app.route('/editar_medicamento/<int:id_produto>', methods=['GET', 'POST'])
@login_required
def editar_medicamento(id_produto):
    conexao = conectar()
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        id_categoria = request.form.get('id_categoria') or None
        preco_custo = request.form.get('preco_custo', 0.0)
        preco_venda = request.form.get('preco_venda', 0.0)
        ativo = 1 if request.form.get('ativo') else 0

        if conexao:
            try:
                cursor = conexao.cursor()
                sql = """
                    UPDATE produtos 
                    SET nome = %s, id_categoria = %s, preco_custo = %s, preco_venda = %s, ativo = %s
                    WHERE id_produto = %s
                """
                cursor.execute(sql, (nome, id_categoria, preco_custo, preco_venda, ativo, id_produto))
                conexao.commit()
                cursor.close()
                flash('Medicamento atualizado com sucesso!', 'success')
                return redirect(url_for('medicamentos'))
            except Error as e:
                conexao.rollback()
                flash(f'Erro ao atualizar medicamento: {e}', 'danger')
            finally:
                conexao.close()

    produto = None
    categorias = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT * FROM produtos WHERE id_produto = %s", (id_produto,))
            produto = cursor.fetchone()

            cursor.execute("SELECT id_categoria, nome FROM categorias ORDER BY nome ASC")
            categorias = cursor.fetchall()
            cursor.close()
        except Error as e:
            print("Erro ao buscar medicamento:", e)
        finally:
            conexao.close()

    if not produto:
        flash('Medicamento não encontrado.', 'danger')
        return redirect(url_for('medicamentos'))

    try:
        return render_template('editar_medicamento.html', produto=produto, categorias=categorias)
    except Exception:
        return render_template('cadastrar_medicamentos.html', produto=produto, categorias=categorias)

# ==========================================
# 9. CLIENTES
# ==========================================
@app.route('/clientes', methods=['GET', 'POST'])
@login_required
def clientes():
    conexao = conectar()
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        cpf = request.form.get('cpf')
        telefone = request.form.get('telefone')
        email = request.form.get('email')

        if conexao:
            try:
                cursor = conexao.cursor()
                sql = """
                    INSERT INTO clientes (nome, cpf, telefone, email)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (nome, cpf, telefone, email))
                conexao.commit()
                cursor.close()
                flash('Cliente cadastrado com sucesso!', 'success')
                return redirect(url_for('clientes'))
            except Error as e:
                conexao.rollback()
                flash(f'Erro ao cadastrar cliente: {e}', 'danger')
            finally:
                conexao.close()

    lista_clientes = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT * FROM clientes ORDER BY nome ASC")
            lista_clientes = cursor.fetchall()
            cursor.close()
        except Error as e:
            print("Erro ao carregar clientes:", e)
        finally:
            conexao.close()

    return render_template('clientes.html', clientes=lista_clientes)

# ==========================================
# 10. CATEGORIAS
# ==========================================
@app.route('/categorias', methods=['GET', 'POST'])
@login_required
def categorias():
    conexao = conectar()
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')

        if conexao:
            try:
                cursor = conexao.cursor()
                sql = "INSERT INTO categorias (nome, descricao) VALUES (%s, %s)"
                cursor.execute(sql, (nome, descricao))
                conexao.commit()
                cursor.close()
                flash('Categoria cadastrada com sucesso!', 'success')
                return redirect(url_for('categorias'))
            except Error as e:
                conexao.rollback()
                flash(f'Erro ao cadastrar categoria: {e}', 'danger')
            finally:
                conexao.close()

    lista_categorias = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT * FROM categorias ORDER BY nome ASC")
            lista_categorias = cursor.fetchall()
            cursor.close()
        except Error as e:
            print("Erro ao carregar categorias:", e)
        finally:
            conexao.close()

    return render_template('categorias.html', categorias=lista_categorias)

# ==========================================
# INICIALIZAÇÃO DA APLICAÇÃO
# ==========================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)