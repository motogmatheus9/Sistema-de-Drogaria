from flask import Flask, render_template, request, redirect, url_for
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)

# ==========================================
# CONEXÃO COM O BANCO DE DADOS
# ==========================================
def conectar():
    try:
        conexao = mysql.connector.connect(
            host="localhost",
            user="root",
            password="69941777",
            database="farmacia_db"
        )
        return conexao
    except Error as erro:
        print("\n[ERRO DE CONEXÃO]:", erro)
        return None

# ==========================================
# 1. DASHBOARD
# ==========================================
@app.route('/')
def dashboard():
    conexao = conectar()
    total_clientes = 0
    total_medicamentos = 0
    total_estoque = 0
    vendas_hoje = 0.0

    if conexao:
        try:
            cursor = conexao.cursor()
            
            # Total de Clientes
            cursor.execute("SELECT COUNT(*) FROM clientes")
            res = cursor.fetchone()
            total_clientes = res[0] if res else 0

            # Total de Produtos
            cursor.execute("SELECT COUNT(*) FROM produtos")
            res = cursor.fetchone()
            total_medicamentos = res[0] if res else 0

            # Total de Itens em Estoque (pela tabela lotes)
            cursor.execute("SELECT SUM(quantidade_atual) FROM lotes")
            res = cursor.fetchone()
            total_estoque = res[0] if res and res[0] else 0

            # Vendas do Dia
            cursor.execute("SELECT SUM(total) FROM vendas WHERE DATE(data_venda) = CURDATE() AND status = 'FINALIZADA'")
            res = cursor.fetchone()
            vendas_hoje = float(res[0]) if res and res[0] else 0.0

            cursor.close()
        except Error as erro:
            print("[ERRO DASHBOARD]:", erro)
        finally:
            conexao.close()

    return render_template(
        'index.html',
        total_clientes=total_clientes,
        total_medicamentos=total_medicamentos,
        total_estoque=total_estoque,
        vendas_hoje=vendas_hoje
    )

# ==========================================
# 2. CLIENTES (LISTAR E CADASTRAR)
# ==========================================
@app.route('/clientes', methods=['GET', 'POST'])
def clientes():
    conexao = conectar()

    if request.method == 'POST':
        nome = request.form.get('nome')
        cpf = request.form.get('cpf')
        telefone = request.form.get('telefone')
        email = request.form.get('email')

        if conexao and nome:
            try:
                cursor = conexao.cursor()
                sql = "INSERT INTO clientes (nome, cpf, telefone, email) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (nome, cpf, telefone, email))
                conexao.commit()
                cursor.close()
            except Error as erro:
                print("[ERRO CADASTRO CLIENTE]:", erro)

    lista_clientes = []
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT * FROM clientes ORDER BY id_cliente DESC")
            lista_clientes = cursor.fetchall()
            cursor.close()
        except Error as erro:
            print("[ERRO BUSCA CLIENTES]:", erro)
        finally:
            conexao.close()

    return render_template('clientes.html', clientes=lista_clientes)

# ==========================================
# 2.1 CLIENTES (TELA DE EDIÇÃO)
# ==========================================
@app.route('/clientes/editar/<int:id>')
def editar_cliente(id):
    conexao = conectar()
    cliente = None
    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            cursor.execute("SELECT * FROM clientes WHERE id_cliente = %s", (id,))
            cliente = cursor.fetchone()
            cursor.close()
        except Error as erro:
            print("[ERRO TELA EDITAR CLIENTE]:", erro)
        finally:
            conexao.close()
            
    return render_template('editar_cliente.html', cliente=cliente)

# ==========================================
# 2.2 CLIENTES (SALVAR ALTERAÇÃO)
# ==========================================
@app.route('/clientes/atualizar/<int:id>', methods=['POST'])
def atualizar_cliente(id):
    nome = request.form.get('nome')
    cpf = request.form.get('cpf')
    telefone = request.form.get('telefone')
    email = request.form.get('email')

    conexao = conectar()
    if conexao:
        try:
            cursor = conexao.cursor()
            sql = """
                UPDATE clientes 
                SET nome = %s, cpf = %s, telefone = %s, email = %s 
                WHERE id_cliente = %s
            """
            cursor.execute(sql, (nome, cpf, telefone, email, id))
            conexao.commit()
            cursor.close()
        except Error as erro:
            print("[ERRO ATUALIZAR CLIENTE]:", erro)
        finally:
            conexao.close()

    return redirect('/clientes')

# ==========================================
# 3. MEDICAMENTOS / PRODUTOS
# ==========================================
@app.route('/medicamentos')
def medicamentos():
    conexao = conectar()
    lista_produtos = []

    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            sql = """
                SELECT 
                    p.id_produto, 
                    p.nome, 
                    COALESCE(c.nome, 'Sem Categoria') AS categoria, 
                    p.fabricante, 
                    p.preco_venda,
                    p.principio_ativo
                FROM produtos p
                LEFT JOIN categorias c ON p.id_categoria = c.id_categoria
                ORDER BY p.id_produto DESC
            """
            cursor.execute(sql)
            lista_produtos = cursor.fetchall()
            cursor.close()
        except Error as erro:
            print("[ERRO BUSCA MEDICAMENTOS]:", erro)
        finally:
            conexao.close()

    return render_template('medicamentos.html', produtos=lista_produtos)

# ==========================================
# 4. ESTOQUE
# ==========================================
@app.route('/estoque')
def estoque():
    conexao = conectar()
    lista_estoque = []

    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            sql = """
                SELECT 
                    p.id_produto, 
                    p.nome, 
                    COALESCE(SUM(l.quantidade_atual), 0) AS estoque,
                    p.estoque_minimo
                FROM produtos p
                LEFT JOIN lotes l ON p.id_produto = l.id_produto
                GROUP BY p.id_produto, p.nome, p.estoque_minimo
            """
            cursor.execute(sql)
            lista_estoque = cursor.fetchall()
            cursor.close()
        except Error as erro:
            print("[ERRO BUSCA ESTOQUE]:", erro)
        finally:
            conexao.close()

    return render_template('estoque.html', estoque=lista_estoque)

# ==========================================
# 5. VENDAS
# ==========================================
@app.route('/vendas')
def vendas():
    conexao = conectar()
    lista_vendas = []

    if conexao:
        try:
            cursor = conexao.cursor(dictionary=True)
            sql = """
                SELECT 
                    v.id_venda, 
                    COALESCE(c.nome, 'Cliente não informado') AS cliente, 
                    v.total, 
                    v.status, 
                    v.data_venda
                FROM vendas v
                LEFT JOIN clientes c ON v.id_cliente = c.id_cliente
                ORDER BY v.id_venda DESC
            """
            cursor.execute(sql)
            lista_vendas = cursor.fetchall()
            cursor.close()
        except Error as erro:
            print("[ERRO BUSCA VENDAS]:", erro)
        finally:
            conexao.close()

    return render_template('vendas.html', vendas=lista_vendas)

# ==========================================
# 6. RELATÓRIOS
# ==========================================
@app.route('/relatorios')
def relatorios():
    return render_template('relatorios.html')

# ==========================================
# INICIALIZAÇÃO DO SERVIDOR (DEVE FICAR POR ÚLTIMO)
# ==========================================
if __name__ == '__main__':
    app.run(debug=True)