import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { X, Check, ChevronRight, ChevronLeft } from 'lucide-react';

const AddEditTeamModal = ({ isOpen, onClose, onSave, team, onNotifyError }) => {
  const [formData, setFormData] = useState({
    name: '',
    selectedMembers: []
  });

  const [allMembers, setAllMembers] = useState([]); // Lista fixa de todos os usuários
  const [loadingUsers, setLoadingUsers] = useState(true);

  const [selectedItems, setSelectedItems] = useState([]);
  const [availableFilter, setAvailableFilter] = useState('');
  const [selectedFilter, setSelectedFilter] = useState('');
  const [saving, setSaving] = useState(false);

  const notifyError = (message) => {
    if (typeof onNotifyError === 'function') {
      onNotifyError(message);
    }
  };

  // Buscar usuários do provedor
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

        if (!token) {
          setAllMembers([]);
          setLoadingUsers(false);
          return;
        }


        // Usar o endpoint correto que retorna apenas os usuários do provedor
        // Adicionamos include_self=true para que o administrador possa se adicionar à equipe
        const response = await fetch('/api/users/my_provider_users/?include_self=true', {
          headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json'
          }
        });


        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Erro ao buscar usuários: ${response.status} - ${errorText}`);
        }

        const data = await response.json();
        const users = data.users || data.results || data;

        // Formatar usuários para o formato esperado
        const formattedUsers = users.map(user => {
          const name = `${user.first_name || user.username} ${user.last_name || ''}`.trim() || user.username;
          return {
            id: user.id,
            name: name
          };
        });

        setAllMembers(formattedUsers); // Armazenar todos os usuários do provedor
      } catch (err) {
        // Se houver erro, deixar lista vazia (sem dados mockados)
        setAllMembers([]);
      } finally {
        setLoadingUsers(false);
      }
    };

    fetchUsers();
  }, []);

  useEffect(() => {
    if (!isOpen) return; // Só executa se o modal estiver aberto

    if (team) {

      // Formatar os membros da equipe para o formato esperado
      const formattedMembers = team.members?.map(member => ({
        id: member.user.id, // Usar o ID do usuário, não do TeamMember
        name: `${member.user.first_name || member.user.username} ${member.user.last_name || ''}`.trim() || member.user.username
      })) || [];


      setFormData({
        name: team.name || '',
        selectedMembers: formattedMembers
      });
    } else {
      setFormData({
        name: '',
        selectedMembers: []
      });
    }
  }, [team, isOpen]);

  // Calcular membros disponíveis dinamicamente
  const availableMembers = allMembers.filter(
    member => !formData.selectedMembers.some(selected => selected.id === member.id)
  );


  const handleInputChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      notifyError('Nome é obrigatório');
      return;
    }

    if (formData.selectedMembers.length === 0) {
      notifyError('Pelo menos um membro deve ser selecionado');
      return;
    }

    setSaving(true);
    try {
      await onSave(formData);
    } finally {
      setSaving(false);
    }
  };


  const filteredAvailable = availableMembers.filter(member =>
    member && member.name && member.name.toLowerCase().includes(availableFilter.toLowerCase())
  );

  const filteredSelected = formData.selectedMembers.filter(member =>
    member && member.name && member.name.toLowerCase().includes(selectedFilter.toLowerCase())
  );


  const toggleAvailableSelection = (member) => {
    setSelectedItems(prev =>
      prev.some(item => item.id === member.id)
        ? prev.filter(item => item.id !== member.id)
        : [...prev, member]
    );
  };

  const toggleSelectedSelection = (member) => {
    setSelectedItems(prev =>
      prev.some(item => item.id === member.id)
        ? prev.filter(item => item.id !== member.id)
        : [...prev, member]
    );
  };

  const moveToSelected = () => {
    const newSelected = [...formData.selectedMembers, ...selectedItems];
    setFormData(prev => ({ ...prev, selectedMembers: newSelected }));
    setSelectedItems([]);
  };

  const moveToAvailable = () => {
    const newSelected = formData.selectedMembers.filter(member =>
      !selectedItems.some(selected => selected.id === member.id)
    );
    setFormData(prev => ({ ...prev, selectedMembers: newSelected }));
    setSelectedItems([]);
  };

  if (!isOpen) return null;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 shadow-2xl backdrop-blur-sm" onClick={onClose}></div>
      <div className="relative bg-background border border-border rounded-lg p-6 max-w-5xl w-full m-4 max-h-[85vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-foreground">Adicionar Equipe</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="space-y-6">
          {/* Nome */}
          <div>
            <Label htmlFor="name" className="text-foreground">Nome *</Label>
            <Input
              id="name"
              placeholder="Nome"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              className="text-foreground"
            />
          </div>

          {/* Membros */}
          <div>
            <Label className="text-foreground">Membros *</Label>

            <div className="grid grid-cols-3 gap-6 mt-2">
              {/* Não Selecionados */}
              <div className="border border-border rounded-lg overflow-hidden bg-muted/50">
                <div className="bg-muted p-4 border-b border-border">
                  <div className="font-medium mb-2 text-foreground">Não Selecionados</div>
                  <div className="text-sm text-muted-foreground mb-2">
                    {loadingUsers ? 'Carregando...' : `${availableMembers.length} agente(s)`}
                  </div>
                  <Input
                    placeholder="Filtro"
                    value={availableFilter}
                    onChange={(e) => setAvailableFilter(e.target.value)}
                    className="text-foreground"
                  />
                </div>
                <div className="p-4">
                  <div className="border border-border rounded h-32 overflow-y-auto bg-background">
                    {loadingUsers ? (
                      <div className="p-2 text-muted-foreground">Carregando usuários...</div>
                    ) : filteredAvailable.length === 0 ? (
                      <div className="p-2 text-muted-foreground">Nenhum usuário disponível</div>
                    ) : (
                      filteredAvailable.map((member) => {
                        const isSelected = selectedItems.some(item => item.id === member.id);
                        return (
                          <div
                            key={member.id}
                            className={`p-2 cursor-pointer hover:bg-muted text-foreground flex items-center justify-between ${isSelected ? 'bg-accent border border-primary' : ''
                              }`}
                            onClick={() => toggleAvailableSelection(member)}
                          >
                            <span>{member.name || 'Nome não disponível'}</span>
                            {isSelected && <Check className="w-4 h-4 text-primary" />}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>

              {/* Botões de Ação */}
              <div className="flex flex-col justify-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={moveToSelected}
                  disabled={selectedItems.filter(item =>
                    availableMembers.some(available => available.id === item.id)
                  ).length === 0}
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={moveToAvailable}
                  disabled={selectedItems.filter(item =>
                    formData.selectedMembers.some(selected => selected.id === item.id)
                  ).length === 0}
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
              </div>

              {/* Selecionados */}
              <div className="border border-border rounded-lg overflow-hidden bg-muted/50">
                <div className="bg-muted p-4 border-b border-border">
                  <div className="font-medium mb-2 text-foreground">Selecionados</div>
                  <div className="text-sm text-muted-foreground mb-2">
                    {formData.selectedMembers.length === 0 ? 'Lista Vazia' : `${formData.selectedMembers.length} agente(s)`}
                  </div>
                  <Input
                    placeholder="Filtro"
                    value={selectedFilter}
                    onChange={(e) => setSelectedFilter(e.target.value)}
                    className="text-foreground"
                  />
                </div>
                <div className="p-4">
                  <div className="border border-border rounded h-32 overflow-y-auto bg-background">
                    {filteredSelected.length === 0 ? (
                      <div className="p-2 text-muted-foreground">Nenhum membro selecionado</div>
                    ) : (
                      filteredSelected.map((member) => {
                        const isSelected = selectedItems.some(item => item.id === member.id);
                        return (
                          <div
                            key={member.id}
                            className={`p-2 cursor-pointer hover:bg-muted text-foreground flex items-center justify-between ${isSelected ? 'bg-accent border border-primary' : ''
                              }`}
                            onClick={() => toggleSelectedSelection(member)}
                          >
                            <span>{member.name || 'Nome não disponível'}</span>
                            {isSelected && <Check className="w-4 h-4 text-primary" />}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Botões de Ação */}
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button variant="outline" onClick={onClose} className="border-red-500/50 hover:bg-red-500/10 text-red-500 font-bold">
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold shadow-lg shadow-emerald-500/20 disabled:opacity-60">
            {saving ? 'Salvando...' : 'Salvar'}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default AddEditTeamModal; 