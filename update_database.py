"""
Script para actualizar la base de datos agregando el campo precio_unitario
"""

from app import app, db
import sqlite3

def update_database():
    with app.app_context():
        # Conectar a la base de datos
        conn = sqlite3.connect('restaurante.db')
        cursor = conn.cursor()
        
        try:
            # Verificar si la columna ya existe
            cursor.execute("PRAGMA table_info(pedido)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'precio_unitario' not in columns:
                print("Agregando columna precio_unitario...")
                cursor.execute("ALTER TABLE pedido ADD COLUMN precio_unitario FLOAT DEFAULT 0")
                conn.commit()
                print("✓ Columna agregada exitosamente")
            else:
                print("✓ La columna precio_unitario ya existe")
            
            conn.close()
            print("\n¡Base de datos actualizada correctamente!")
            
        except Exception as e:
            print(f"Error al actualizar la base de datos: {e}")
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    update_database()