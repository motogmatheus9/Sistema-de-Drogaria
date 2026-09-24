from flask import Flask, render_template, request, redirect, url_for
import mysql.connector

import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

@app.route("/")
def home():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM produtos")
        total_medicamentos = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM clientes")
        total_clientes = cursor.fetchone()['total']

        cursor.execute("SELECT COALESCE(SUM(total), 0) AS total FROM vendas WHERE DATE(data_venda) = CURDATE()")
        vendas_hoje = cursor.fetchone()['total']

        cursor.execute("SELECT COALESCE(SUM(quantidade_atual), 0) AS total FROM lotes")
        total_estoque = cursor.fetchone()['total']

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Erro no banco: {e}")
        total_medicamentos, total_clientes, vendas_hoje, total_estoque = 0, 0, 0.0, 0

    return render_template(
        "index.html",
        total_medicamentos=total_medicamentos,
        total_clientes=total_clientes,
        vendas_hoje=vendas_hoje,
        total_estoque=total_estoque
    )

@app.route("/clientes")
def listar_clientes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM clientes ORDER BY id_cliente DESC")
        clientes = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao buscar clientes: {e}")
        clientes = []

    return render_template("clientes.html", clientes=clientes, cliente_edit=None)

@app.route("/clientes/cadastrar", methods=["POST"])
def cadastrar_cliente():
    nome = request.form.get("nome")
    cpf = request.form.get("cpf")
    telefone = request.form.get("telefone")
    email = request.form.get("email")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO clientes (nome, cpf, telefone, email) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql, (nome, cpf, telefone, email))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao cadastrar cliente: {e}")

    return redirect(url_for("listar_clientes"))

@app.route("/clientes/editar/<int:id_cliente>")
def editar_cliente(id_cliente):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM clientes ORDER BY id_cliente DESC")
        clientes = cursor.fetchall()

        cursor.execute("SELECT * FROM clientes WHERE id_cliente = %s", (id_cliente,))
        cliente_edit = cursor.fetchone()

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao carregar cliente: {e}")
        clientes, cliente_edit = [], None

    return render_template("clientes.html", clientes=clientes, cliente_edit=cliente_edit)

@app.route("/clientes/atualizar/<int:id_cliente>", methods=["POST"])
def atualizar_cliente(id_cliente):
    nome = request.form.get("nome")
    cpf = request.form.get("cpf")
    telefone = request.form.get("telefone")
    email = request.form.get("email")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE clientes SET nome = %s, cpf = %s, telefone = %s, email = %s WHERE id_cliente = %s"
        cursor.execute(sql, (nome, cpf, telefone, email, id_cliente))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao atualizar cliente: {e}")

    return redirect(url_for("listar_clientes"))

if __name__ == "__main__":
    app.run(debug=True)