
import os

file_path = r'e:\niochat\backend\conversations\views.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
found = False
for i, line in enumerate(lines):
    # Procurar a linha específica dentro do método dashboard_stats
    if 'if not provedor:' in line and i > 380 and i < 450:
        # Verificar se é a segunda ocorrência (a primeira é do superadmin)
        # Na verdade, vamos procurar o bloco inteiro
        if i + 1 < len(lines) and 'if hasattr(user, \'provedor_id\')' in lines[i+1]:
            indent = line[:line.find('if')]
            new_lines.append(line)
            new_lines.append(lines[i+1])
            new_lines.append(lines[i+2])
            
            # Inserir a nova lógica
            new_lines.append(f"{indent}    if not provedor:\n")
            new_lines.append(f"{indent}        from .models import TeamMember\n")
            new_lines.append(f"{indent}        tm = TeamMember.objects.filter(user=user).select_related('team__provedor').first()\n")
            new_lines.append(f"{indent}        if tm and tm.team:\n")
            new_lines.append(f"{indent}            provedor = tm.team.provedor\n")
            
            found = True
            # Pular as linhas originais já tratadas
            # O loop vai processar o restante a partir de i+3
            continue
    
    # Se já processamos o bloco, e chegamos na linha de erro 400 antiga
    if found and 'return Response({\'error\': \'Provedor não encontrado\'}, status=400)' in line:
        indent = line[:line.find('return')]
        new_lines.append(f"{indent}return Response({{'error': 'Provedor não identificado para este atendente'}}, status=400)\n")
        found = False # reset para não pegar outros returns por engano
        continue
        
    new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Patch aplicado com sucesso!")
