# Configuração da IA

O NioChat utiliza OpenAI GPT para atendimento inteligente, transcrição de áudio e análise de sentimento. Este guia explica como configurar e usar a IA.

## Visão Geral

### Funcionalidades da IA
- **Atendimento Automatizado**: Respostas inteligentes para clientes
- **Transcrição de Áudio**: Conversão de mensagens de voz para texto
- **Consulta SGP**: Integração automática com sistema de gestão
- **Análise de Sentimento**: Interpretação de feedback CSAT
- **Function Calls**: Execução automática de funções

### Arquitetura
```
Cliente → WhatsApp → NioChat → OpenAI → SGP → Resposta
   ↓         ↓         ↓         ↓      ↓       ↓
Mensagem → Webhook → IA → Function → Dados → Cliente
```

## Configuração Inicial

### 1. Obter Chave OpenAI
```bash
# Acessar OpenAI
https://platform.openai.com

# Criar API Key
- Acesse API Keys
- Clique em "Create new secret key"
- Copie a chave gerada
```

### 2. Configurar Variáveis
```env
# Adicionar ao .env
OPENAI_API_KEY=sk-sua_chave_openai_aqui
OPENAI_MODEL=gpt-4
OPENAI_MAX_TOKENS=2000
OPENAI_TEMPERATURE=0.7
```

### 3. Configurar Django
```python
# settings.py
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
OPENAI_MAX_TOKENS = int(os.getenv('OPENAI_MAX_TOKENS', '2000'))
OPENAI_TEMPERATURE = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
```

## Serviço OpenAI

### 1. Classe Principal
```python
# core/openai_service.py
import openai
from django.conf import settings
from typing import Dict, Any, Optional, List

class OpenAIService:
    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.max_tokens = settings.OPENAI_MAX_TOKENS
        self.temperature = settings.OPENAI_TEMPERATURE
    
    def generate_response(self, message: str, context: Dict[str, Any]) -> str:
        """Gerar resposta da IA"""
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt(context)},
                    {"role": "user", "content": message}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Erro ao gerar resposta: {e}")
            return "Desculpe, ocorreu um erro. Tente novamente."
    
    def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcrever áudio para texto"""
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript = openai.Audio.transcribe(
                    model="whisper-1",
                    file=audio_file
                )
                return transcript.text
        except Exception as e:
            print(f"Erro na transcrição: {e}")
            return ""
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analisar sentimento do texto"""
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_sentiment_prompt()},
                    {"role": "user", "content": text}
                ],
                max_tokens=100,
                temperature=0.1
            )
            
            return self._parse_sentiment_response(response.choices[0].message.content)
        except Exception as e:
            print(f"Erro na análise de sentimento: {e}")
            return {"emoji": "😐", "rating": 3}
    
    def _get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Obter prompt do sistema"""
        return f"""
        Você é um assistente virtual especializado em atendimento ao cliente.
        
        Contexto:
        - Provedor: {context.get('provedor_name', 'NioChat')}
        - Cliente: {context.get('contact_name', 'Cliente')}
        - Conversa: {context.get('conversation_id', 'Nova')}
        
        Instruções:
        1. Seja sempre cordial e prestativo
        2. Use informações do SGP quando disponível
        3. Se não souber algo, peça mais informações
        4. Mantenha o tom profissional mas amigável
        5. Use emojis moderadamente
        """
    
    def _get_sentiment_prompt(self) -> str:
        """Obter prompt para análise de sentimento"""
        return """
        Analise o sentimento do texto e retorne:
        - emoji: 😡 (1), 😕 (2), 😐 (3), 🙂 (4), 🤩 (5)
        - rating: número de 1 a 5
        
        Escala:
        1 = Muito insatisfeito (😡)
        2 = Insatisfeito (😕)
        3 = Neutro (😐)
        4 = Satisfeito (🙂)
        5 = Muito satisfeito (🤩)
        
        Responda apenas: {"emoji": "😐", "rating": 3}
        """
    
    def _parse_sentiment_response(self, response: str) -> Dict[str, Any]:
        """Parsear resposta de sentimento"""
        try:
            import json
            return json.loads(response)
        except:
            return {"emoji": "😐", "rating": 3}
```

### 2. Uso no Django
```python
# Em views.py
from core.openai_service import OpenAIService

def process_message(request):
    message = request.POST.get('message')
    conversation = Conversation.objects.get(id=request.POST.get('conversation_id'))
    
    # Gerar resposta da IA
    openai_service = OpenAIService()
    context = {
        'provedor_name': conversation.provedor.name,
        'contact_name': conversation.contact.name,
        'conversation_id': conversation.id
    }
    
    response = openai_service.generate_response(message, context)
    
    return JsonResponse({'response': response})
```

## Function Calls

### 1. Configurar Funções
```python
# core/openai_service.py
def generate_response_with_functions(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Gerar resposta com function calls"""
    try:
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._get_system_prompt(context)},
                {"role": "user", "content": message}
            ],
            functions=self._get_functions(),
            function_call="auto",
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        
        return {
            'response': response.choices[0].message.content,
            'function_calls': response.choices[0].message.get('function_calls', [])
        }
    except Exception as e:
        print(f"Erro ao gerar resposta: {e}")
        return {'response': 'Desculpe, ocorreu um erro.', 'function_calls': []}
    
def _get_functions(self) -> List[Dict[str, Any]]:
    """Obter funções disponíveis"""
    return [
        {
            "name": "consultar_cliente_sgp",
            "description": "Consultar dados do cliente no SGP",
            "parameters": {
                "type": "object",
                "properties": {
                    "cpf_cnpj": {
                        "type": "string",
                        "description": "CPF ou CNPJ do cliente"
                    }
                },
                "required": ["cpf_cnpj"]
            }
        },
        {
            "name": "verificar_acesso_sgp",
            "description": "Verificar status de acesso do cliente",
            "parameters": {
                "type": "object",
                "properties": {
                    "contrato": {
                        "type": "string",
                        "description": "Número do contrato"
                    }
                },
                "required": ["contrato"]
            }
        },
        {
            "name": "gerar_fatura_completa",
            "description": "Gerar fatura completa do cliente",
            "parameters": {
                "type": "object",
                "properties": {
                    "contrato": {
                        "type": "string",
                        "description": "Número do contrato"
                    }
                },
                "required": ["contrato"]
            }
        },
        {
            "name": "criar_chamado_tecnico",
            "description": "Criar chamado técnico para o cliente",
            "parameters": {
                "type": "object",
                "properties": {
                    "cpf_cnpj": {
                        "type": "string",
                        "description": "CPF ou CNPJ do cliente"
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Motivo do chamado"
                    },
                    "sintomas": {
                        "type": "string",
                        "description": "Sintomas relatados"
                    }
                },
                "required": ["cpf_cnpj", "motivo", "sintomas"]
            }
        }
    ]
```

### 2. Executar Function Calls
```python
# core/openai_service.py
def execute_function_call(self, function_name: str, parameters: Dict[str, Any]) -> str:
    """Executar function call"""
    try:
        if function_name == "consultar_cliente_sgp":
            return self._consultar_cliente_sgp(parameters)
        elif function_name == "verificar_acesso_sgp":
            return self._verificar_acesso_sgp(parameters)
        elif function_name == "gerar_fatura_completa":
            return self._gerar_fatura_completa(parameters)
        elif function_name == "criar_chamado_tecnico":
            return self._criar_chamado_tecnico(parameters)
        else:
            return "Função não encontrada"
    except Exception as e:
        print(f"Erro ao executar função {function_name}: {e}")
        return "Erro ao executar função"
    
def _consultar_cliente_sgp(self, parameters: Dict[str, Any]) -> str:
    """Consultar cliente no SGP"""
    cpf_cnpj = parameters.get('cpf_cnpj')
    
    # Integração com SGP
    from core.sgp_client import SGPClient
    sgp_client = SGPClient()
    cliente = sgp_client.consultar_cliente(cpf_cnpj)
    
    if cliente:
        return f"Cliente encontrado: {cliente['nome']} - Contrato: {cliente['contrato']}"
    else:
        return "Cliente não encontrado no SGP"
    
def _verificar_acesso_sgp(self, parameters: Dict[str, Any]) -> str:
    """Verificar acesso no SGP"""
    contrato = parameters.get('contrato')
    
    from core.sgp_client import SGPClient
    sgp_client = SGPClient()
    status = sgp_client.verificar_acesso(contrato)
    
    return f"Status do acesso: {status}"
    
def _gerar_fatura_completa(self, parameters: Dict[str, Any]) -> str:
    """Gerar fatura completa"""
    contrato = parameters.get('contrato')
    
    from core.sgp_client import SGPClient
    sgp_client = SGPClient()
    fatura = sgp_client.gerar_fatura(contrato)
    
    if fatura:
        return f"Fatura gerada: {fatura['valor']} - Vencimento: {fatura['vencimento']}"
    else:
        return "Erro ao gerar fatura"
    
def _criar_chamado_tecnico(self, parameters: Dict[str, Any]) -> str:
    """Criar chamado técnico"""
    cpf_cnpj = parameters.get('cpf_cnpj')
    motivo = parameters.get('motivo')
    sintomas = parameters.get('sintomas')
    
    from core.sgp_client import SGPClient
    sgp_client = SGPClient()
    chamado = sgp_client.criar_chamado(cpf_cnpj, motivo, sintomas)
    
    if chamado:
        return f"Chamado criado: {chamado['numero']} - Status: {chamado['status']}"
    else:
        return "Erro ao criar chamado"
```

## Transcrição de Áudio

### 1. Processar Áudio
```python
# conversations/views.py
def process_audio_message(request):
    audio_file = request.FILES.get('audio')
    conversation_id = request.POST.get('conversation_id')
    
    # Salvar arquivo temporário
    temp_path = f"/tmp/audio_{conversation_id}.ogg"
    with open(temp_path, 'wb') as f:
        for chunk in audio_file.chunks():
            f.write(chunk)
    
    # Transcrever com OpenAI
    openai_service = OpenAIService()
    transcript = openai_service.transcribe_audio(temp_path)
    
    # Limpar arquivo temporário
    os.remove(temp_path)
    
    # Processar transcrição
    if transcript:
        # Salvar mensagem transcrita
        message = Message.objects.create(
            conversation_id=conversation_id,
            content=transcript,
            message_type='text'
        )
        
        # Processar com IA
        response = openai_service.generate_response(transcript, context)
        
        return JsonResponse({
            'transcript': transcript,
            'response': response
        })
    
    return JsonResponse({'error': 'Erro na transcrição'})
```

### 2. Configurar Whisper
```python
# core/openai_service.py
def transcribe_audio_advanced(self, audio_file_path: str, language: str = 'pt') -> str:
    """Transcrever áudio com configurações avançadas"""
    try:
        with open(audio_file_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="text",
                temperature=0.0
            )
            return transcript
    except Exception as e:
        print(f"Erro na transcrição: {e}")
        return ""
```

## Análise de Sentimento

### 1. Sistema CSAT
```python
# conversations/csat_automation.py
from core.openai_service import OpenAIService

class CSATAutomationService:
    @classmethod
    def process_csat_response(cls, message_text: str, conversation, contact):
        """Processar resposta CSAT"""
        openai_service = OpenAIService()
        
        # Analisar sentimento
        sentiment = openai_service.analyze_sentiment(message_text)
        
        # Corrigir rating se necessário
        if any(word in message_text.lower() for word in ['péssimo', 'horrível', 'terrível']):
            if sentiment['rating'] != 1:
                sentiment = {'emoji': '😡', 'rating': 1}
        
        # Salvar feedback
        feedback = CSATFeedback.objects.create(
            conversation=conversation,
            contact=contact,
            emoji_rating=sentiment['emoji'],
            rating_value=sentiment['rating'],
            original_message=message_text
        )
        
        # Gerar resposta personalizada
        response = openai_service.generate_csat_response(
            sentiment['rating'], 
            contact.name
        )
        
        return feedback, response
```

### 2. Resposta Personalizada
```python
# core/openai_service.py
def generate_csat_response(self, rating: int, contact_name: str) -> str:
    """Gerar resposta personalizada para CSAT"""
    responses = {
        1: f"😔 Sinto muito que seu atendimento não foi bom, {contact_name}! Estamos sempre melhorando e esperamos te atender melhor na próxima vez.",
        2: f"😕 Poxa, {contact_name}, sentimos que não tenha gostado. Sua opinião é importante para melhorarmos!",
        3: f"🙂 Obrigado pelo seu feedback, {contact_name}! Vamos trabalhar para te surpreender da próxima vez.",
        4: f"😄 Que bom saber disso, {contact_name}! Ficamos felizes que seu atendimento foi bom!",
        5: f"🤩 Maravilha, {contact_name}! Agradecemos por sua avaliação e ficamos felizes com sua satisfação!"
    }
    
    return responses.get(rating, responses[3])
```

## Configurações Avançadas

### 1. Prompts Personalizados
```python
# core/openai_service.py
def _get_custom_prompt(self, provedor_id: int) -> str:
    """Obter prompt personalizado por provedor"""
    try:
        provedor = Provedor.objects.get(id=provedor_id)
        return f"""
        Você é um assistente virtual da {provedor.name}.
        
        Especialização: {provedor.description}
        Tom: {provedor.tone or 'profissional e amigável'}
        Linguagem: {provedor.language or 'português brasileiro'}
        
        Instruções específicas:
        {provedor.ai_instructions or 'Seja sempre prestativo e resolva os problemas do cliente.'}
        """
    except:
        return self._get_system_prompt({})
```

### 2. Rate Limiting
```python
# core/openai_service.py
from django.core.cache import cache

def generate_response_with_rate_limit(self, message: str, context: Dict[str, Any]) -> str:
    """Gerar resposta com rate limiting"""
    user_id = context.get('user_id')
    cache_key = f"openai_rate_limit_{user_id}"
    
    # Verificar rate limit
    if cache.get(cache_key):
        return "Muitas requisições. Aguarde um momento."
    
    # Definir rate limit (1 requisição por segundo)
    cache.set(cache_key, True, 1)
    
    return self.generate_response(message, context)
```

### 3. Logging e Monitoramento
```python
# core/openai_service.py
import logging

logger = logging.getLogger(__name__)

def generate_response(self, message: str, context: Dict[str, Any]) -> str:
    """Gerar resposta com logging"""
    start_time = time.time()
    
    try:
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._get_system_prompt(context)},
                {"role": "user", "content": message}
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        
        # Log de sucesso
        logger.info(f"Resposta gerada em {time.time() - start_time:.2f}s")
        
        return response.choices[0].message.content
        
    except Exception as e:
        # Log de erro
        logger.error(f"Erro ao gerar resposta: {e}")
        return "Desculpe, ocorreu um erro. Tente novamente."
```

## Troubleshooting

### 1. Problemas Comuns
```bash
# Verificar chave OpenAI
curl -H "Authorization: Bearer sk-sua_chave" https://api.openai.com/v1/models

# Verificar créditos
curl -H "Authorization: Bearer sk-sua_chave" https://api.openai.com/v1/usage
```

### 2. Logs de Debug
```python
# Testar conexão
from core.openai_service import OpenAIService
openai_service = OpenAIService()
print(openai_service.test_connection())
```

### 3. Monitoramento
```python
# Verificar uso da API
def check_openai_usage():
    try:
        usage = openai.Usage.retrieve()
        print(f"Tokens usados: {usage.total_tokens}")
        print(f"Custo: ${usage.total_cost}")
    except Exception as e:
        print(f"Erro ao verificar uso: {e}")
```

## Próximos Passos

1. [Function Calls](function-calls.md) - Configure function calls
2. [SGP Integration](sgp-integration.md) - Configure integração SGP
3. [Transcrição](transcription.md) - Configure transcrição