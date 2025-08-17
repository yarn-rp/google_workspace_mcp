# 📧 Blueprint Agent Email Guide

## 🎯 **Problema Resuelto**

Los tools de Google Workspace requieren un parámetro `user_google_email`, pero ahora tenemos acceso al email del Blueprint agent en Firebase. Esta guía explica cómo usar el email automáticamente.

## 🔧 **Cómo Funciona**

### **1. Middleware Automático**
El middleware simple ahora:
- ✅ Extrae el `X-Blueprint-Agent-Id` del header
- ✅ Busca el agent en Firebase (`agents/{agent_id}`)
- ✅ Extrae tanto el `access_token` como el `email` del agent
- ✅ Loggea el email disponible para referencia

### **2. Logs Informativos**
Cuando te conectes, verás logs como:
```
INFO:auth.simple_middleware:✅ Added Google access token for agent: bea33dad-9b5b-4fe1-8d45-634085aa5771
INFO:auth.simple_middleware:📧 Agent email available: user@example.com
INFO:auth.simple_middleware:💡 To use tools, pass user_google_email='user@example.com' as parameter
```

## 📱 **Uso en Cursor**

### **Configuración MCP (ya tienes esto):**
```json
{
  "mcpServers": {
    "google-workspace-test": {
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "X-Blueprint-Agent-Id": "bea33dad-9b5b-4fe1-8d45-634085aa5771"
      }
    }
  }
}
```

### **Usando Tools con Email:**

#### **❌ Antes (fallaba):**
```
get_events()  // Error: No valid 'user_google_email' provided
```

#### **✅ Ahora (funciona):**
```
get_events(user_google_email="user@example.com")
```

## 🚀 **Ejemplos de Tools**

### **📅 Calendar:**
```javascript
// Obtener eventos del calendario
get_events({
  user_google_email: "user@example.com",
  time_min: "2024-01-01T00:00:00Z",
  max_results: 10
})

// Crear evento
create_event({
  user_google_email: "user@example.com",
  summary: "Meeting with team",
  start_time: "2024-01-15T10:00:00Z",
  end_time: "2024-01-15T11:00:00Z"
})
```

### **📧 Gmail:**
```javascript
// Buscar emails
search_gmail_messages({
  user_google_email: "user@example.com",
  query: "from:boss@company.com",
  page_size: 5
})

// Enviar email
send_gmail_message({
  user_google_email: "user@example.com",
  to: "colleague@company.com",
  subject: "Project Update",
  body: "Here's the latest update..."
})
```

### **📁 Drive:**
```javascript
// Buscar archivos
search_drive_files({
  user_google_email: "user@example.com",
  query: "name contains 'report'",
  page_size: 10
})

// Crear archivo
create_drive_file({
  user_google_email: "user@example.com",
  file_name: "new-document.txt",
  content: "Hello world!"
})
```

## 🔍 **Debugging**

### **Ver el Email del Agent:**
1. Conéctate a MCP desde Cursor
2. Busca en los logs del servidor:
   ```
   INFO:auth.simple_middleware:📧 Agent email available: tu-email@example.com
   ```
3. Usa ese email en los tool calls

### **Si no aparece el email:**
- ✅ Verifica que el agent existe en Firebase
- ✅ Verifica que el campo `email` existe en el document del agent
- ✅ Revisa los logs para errores de Firebase

## 💡 **Tips**

1. **Copia el email de los logs** - Es la forma más fácil de obtenerlo
2. **Guarda el email** - Puedes reutilizarlo en múltiples tool calls
3. **Usa autocompletado** - Cursor recordará el email después del primer uso

## 🎉 **Beneficios**

- ✅ **Automático**: El middleware extrae el email automáticamente
- ✅ **Visible**: Los logs muestran claramente qué email usar
- ✅ **Simple**: Solo necesitas copiar/pegar el email en los tool calls
- ✅ **Confiable**: Usa el email real asociado al Blueprint agent
