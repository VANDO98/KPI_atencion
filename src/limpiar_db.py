import os
import sys
import sqlite3
import database as db # Reutilizar la ruta absoluta

DB_NAME = db.DB_NAME

def limpiar_base_de_datos():
    if not os.path.exists(DB_NAME):
        print(f"La base de datos '{DB_NAME}' no existe.")
        return

    print("⚠️  ADVERTENCIA: Esta acción eliminará TODOS los registros de requerimientos_originales.")
    confirmacion = input("¿Estás seguro de que deseas continuar? (S_para_sí/Cualquier_tecla_para_cancelar): ")
    
    if confirmacion.upper() == 'S':
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # Limpiar la tabla
            cursor.execute("DELETE FROM requerimientos_originales")
            conn.commit()  # Guardar cambios primero para cerrar la transacción
            
            # Opcional: Ejecutar VACUUM para reducir el tamaño del archivo
            cursor.execute("VACUUM")
            print("✅ Base de datos limpiada correctamente. Se eliminaron todos los registros.")
            
        except Exception as e:
            print(f"❌ Error al limpiar la base de datos: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
    else:
        print("❌ Operación cancelada por el usuario.")

if __name__ == "__main__":
    limpiar_base_de_datos()
