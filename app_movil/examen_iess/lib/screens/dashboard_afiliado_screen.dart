import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/security_utils.dart';
import 'login_screen.dart';

class DashboardAfiliadoScreen extends StatefulWidget {
  const DashboardAfiliadoScreen({super.key});

  @override
  State<DashboardAfiliadoScreen> createState() => _DashboardAfiliadoScreenState();
}

class _DashboardAfiliadoScreenState extends State<DashboardAfiliadoScreen> {
  final _api = ApiService();

  int _currentTabIndex = 0;
  bool _loading = false;

  // Beneficiario seleccionado (Anti-BOLA Req. 106)
  String _beneficiarioCedula = '';
  List<DelegacionModel> _delegaciones = [];

  // Pestaña 0: Agendar Cita
  List<String> _establecimientos = [];
  List<String> _especialidades = [];
  String _selectedEstablecimiento = '';
  String _selectedEspecialidad = '';
  DateTime _selectedFecha = DateTime.now().add(const Duration(days: 2));
  List<TurnoSlotModel> _grillaSlots = [];
  TurnoSlotModel? _selectedSlot;
  bool _loadingSlots = false;
  bool _submittingTurno = false;

  // Pestaña 1: Mis Turnos
  List<TurnoModel> _turnos = [];
  bool _loadingTurnos = false;

  // Pestaña 2: Notificaciones
  List<NotificacionModel> _notificaciones = [];
  bool _loadingNotificaciones = false;
  Timer? _slotsPollTimer;

  @override
  void initState() {
    super.initState();
    _beneficiarioCedula = _api.currentUser?.cedula ?? '';
    _inicializarDatos();
    _slotsPollTimer = Timer.periodic(const Duration(seconds: 12), (_) {
      if (_currentTabIndex == 0 && mounted && !_loadingSlots) {
        _consultarSlots();
      }
    });
  }

  @override
  void dispose() {
    _slotsPollTimer?.cancel();
    super.dispose();
  }

  Future<void> _inicializarDatos() async {
    setState(() => _loading = true);
    await Future.wait([
      _cargarDelegaciones(),
      _cargarCatalogoYDisponibilidad(),
      _cargarMisTurnos(),
      _cargarNotificaciones(),
    ]);
    if (mounted) setState(() => _loading = false);
  }

  String _formatDateIso(DateTime dt) {
    final yyyy = dt.year.toString();
    final mm = dt.month.toString().padLeft(2, '0');
    final dd = dt.day.toString().padLeft(2, '0');
    return '$yyyy-$mm-$dd';
  }

  // ==========================================
  // CARGA DE DATOS
  // ==========================================

  Future<void> _cargarDelegaciones() async {
    try {
      final list = await _api.getDelegaciones();
      if (mounted) setState(() => _delegaciones = list);
    } catch (_) {}
  }

  Future<void> _cargarCatalogoYDisponibilidad() async {
    try {
      final data = await _api.getDisponibilidad();
      final ests = List<String>.from(data['establecimientos'] ?? []);
      final esps = List<String>.from(data['especialidades'] ?? []);

      if (mounted) {
        setState(() {
          _establecimientos = ests;
          _especialidades = esps;
          if (_establecimientos.isNotEmpty && _selectedEstablecimiento.isEmpty) {
            _selectedEstablecimiento = _establecimientos.first;
          }
          if (_especialidades.isNotEmpty && _selectedEspecialidad.isEmpty) {
            _selectedEspecialidad = _especialidades.first;
          }
        });
        _consultarSlots();
      }
    } catch (e) {
      _showSnackbar('Error al cargar catálogo de atención: $e');
    }
  }

  Future<void> _consultarSlots() async {
    if (_selectedEstablecimiento.isEmpty || _selectedEspecialidad.isEmpty) return;

    setState(() {
      _loadingSlots = true;
      _selectedSlot = null;
    });

    try {
      final data = await _api.getDisponibilidad(
        establecimiento: _selectedEstablecimiento,
        especialidad: _selectedEspecialidad,
        fecha: _formatDateIso(_selectedFecha),
      );

      final rawSlots = data['grilla_turnos'] ?? data['horarios_disponibles'] ?? [];
      final list = (rawSlots as List).map((e) => TurnoSlotModel.fromJson(Map<String, dynamic>.from(e))).toList();

      if (mounted) {
        setState(() => _grillaSlots = list);
      }
    } catch (e) {
      if (mounted) setState(() => _grillaSlots = []);
      _showSnackbar('Error al consultar horarios: $e');
    } finally {
      if (mounted) setState(() => _loadingSlots = false);
    }
  }

  Future<void> _cargarMisTurnos() async {
    if (_beneficiarioCedula.isEmpty) return;
    setState(() => _loadingTurnos = true);
    try {
      final list = await _api.getMisTurnos(_beneficiarioCedula);
      if (mounted) setState(() => _turnos = list);
    } catch (e) {
      _showSnackbar('Error al cargar turnos: $e');
    } finally {
      if (mounted) setState(() => _loadingTurnos = false);
    }
  }

  Future<void> _cargarNotificaciones() async {
    setState(() => _loadingNotificaciones = true);
    try {
      final list = await _api.getNotificaciones();
      if (mounted) setState(() => _notificaciones = list);
    } catch (_) {
    } finally {
      if (mounted) setState(() => _loadingNotificaciones = false);
    }
  }

  void _showSnackbar(String msg, {bool isError = true}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: isError ? Colors.red.shade800 : Colors.green.shade800,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  // ==========================================
  // ACCIONES OPERATIVAS
  // ==========================================

  Future<void> _confirmarReserva() async {
    if (_selectedSlot == null || _submittingTurno) return;

    setState(() => _submittingTurno = true);
    try {
      await _api.reservarTurno(
        beneficiarioCedula: _beneficiarioCedula,
        medicoCedula: _selectedSlot!.medicoCedula,
        establecimiento: _selectedSlot!.establecimiento,
        especialidad: _selectedSlot!.especialidad,
        fecha: _selectedSlot!.fecha,
        hora: _selectedSlot!.hora,
      );

      _showSnackbar('Cita reservada exitosamente para ${_selectedSlot!.fecha} a las ${_selectedSlot!.hora}', isError: false);
      setState(() => _selectedSlot = null);

      await Future.wait([
        _consultarSlots(),
        _cargarMisTurnos(),
        _cargarNotificaciones(),
      ]);

      // Cambiar a la pestaña de Mis Turnos para visualizar la cita recién agendada
      setState(() => _currentTabIndex = 1);
    } on ApiException catch (e) {
      _showSnackbar(e.message);
      setState(() => _selectedSlot = null);
      _consultarSlots();
    } catch (e) {
      _showSnackbar('No se pudo reservar la cita: $e');
      setState(() => _selectedSlot = null);
      _consultarSlots();
    } finally {
      if (mounted) setState(() => _submittingTurno = false);
    }
  }

  Future<void> _cancelarTurno(TurnoModel turno) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancelar Cita Médica', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        content: Text('¿Está seguro de cancelar el turno de ${turno.especialidad} del ${turno.fecha} a las ${turno.hora}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Volver')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Confirmar Cancelación', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (confirm != true) return;

    try {
      await _api.cancelarTurno(turno.id);
      _showSnackbar('Turno cancelado correctamente.', isError: false);
      await Future.wait([
        _cargarMisTurnos(),
        _cargarNotificaciones(),
        _consultarSlots(),
      ]);
    } on ApiException catch (e) {
      _showSnackbar(e.message);
    }
  }

  Future<void> _reprogramarTurnoDialog(TurnoModel turno) async {
    DateTime nuevaFecha = DateTime.now().add(const Duration(days: 2));
    List<TurnoSlotModel> slotsDisponibles = [];
    TurnoSlotModel? slotElegido;
    bool loadingModal = false;

    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setModalState) {
          Future<void> consultarModalSlots(DateTime f) async {
            setModalState(() {
              loadingModal = true;
              slotElegido = null;
            });
            try {
              final data = await _api.getDisponibilidad(
                establecimiento: turno.establecimiento,
                especialidad: turno.especialidad,
                fecha: _formatDateIso(f),
              );
              final raw = data['horarios_disponibles'] ?? [];
              final list = (raw as List).map((e) => TurnoSlotModel.fromJson(Map<String, dynamic>.from(e))).toList();
              setModalState(() => slotsDisponibles = list);
            } catch (_) {
              setModalState(() => slotsDisponibles = []);
            } finally {
              setModalState(() => loadingModal = false);
            }
          }

          return AlertDialog(
            title: Text('Reprogramar Cita · ${turno.especialidad}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
            content: SizedBox(
              width: double.maxFinite,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(turno.establecimiento, style: const TextStyle(fontSize: 12, color: Colors.black54)),
                    const SizedBox(height: 12),
                    const Text('Seleccione nueva fecha (mínimo 24h de anticipación):', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 6),
                    OutlinedButton.icon(
                      icon: const Icon(Icons.calendar_today, size: 16),
                      label: Text(_formatDateIso(nuevaFecha)),
                      onPressed: () async {
                        final picked = await showDatePicker(
                          context: context,
                          initialDate: nuevaFecha,
                          firstDate: DateTime.now().add(const Duration(days: 1)),
                          lastDate: DateTime.now().add(const Duration(days: 365)),
                        );
                        if (picked != null) {
                          setModalState(() => nuevaFecha = picked);
                          await consultarModalSlots(picked);
                        }
                      },
                    ),
                    const SizedBox(height: 14),
                    const Text('Horarios libres disponibles:', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 6),
                    if (loadingModal)
                      const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator(strokeWidth: 2)))
                    else if (slotsDisponibles.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 8),
                        child: Text('Sin cupos libres para esta fecha. Seleccione otra fecha futura.', style: TextStyle(fontSize: 11, color: Colors.grey)),
                      )
                    else
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: slotsDisponibles.map((s) {
                          final isSelected = slotElegido?.hora == s.hora;
                          return ChoiceChip(
                            label: Text(s.hora, style: TextStyle(fontSize: 11, color: isSelected ? Colors.white : Colors.black87)),
                            selected: isSelected,
                            selectedColor: const Color(0xFF0B3B60),
                            onSelected: (val) => setModalState(() => slotElegido = val ? s : null),
                          );
                        }).toList(),
                      ),
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
              ElevatedButton(
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0B3B60)),
                onPressed: slotElegido == null
                    ? null
                    : () async {
                        try {
                          await _api.reprogramarTurno(
                            turno.id,
                            fecha: _formatDateIso(nuevaFecha),
                            hora: slotElegido!.hora,
                            medicoCedula: slotElegido!.medicoCedula,
                          );
                          if (!ctx.mounted) return;
                          Navigator.pop(ctx);
                          if (!mounted) return;
                          _showSnackbar('Turno reprogramado para ${_formatDateIso(nuevaFecha)} a las ${slotElegido!.hora}', isError: false);
                          await Future.wait([
                            _cargarMisTurnos(),
                            _cargarNotificaciones(),
                            _consultarSlots(),
                          ]);
                        } on ApiException catch (e) {
                          if (mounted) _showSnackbar(e.message);
                        }
                      },
                child: const Text('Guardar Horario', style: TextStyle(color: Colors.white)),
              ),
            ],
          );
        },
      ),
    );
  }

  // ==========================================
  // MODAL VINCULAR FAMILIAR ADULTO CON OTP (REQ. 106)
  // ==========================================

  void _abrirModalVincularFamiliar() {
    final cedulaCtrl = TextEditingController(text: '1710000025');
    final otpCtrl = TextEditingController();
    bool otpEnviado = false;
    String debugOtp = '';
    bool loading = false;
    String? error;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setModalState) {
          final ced = cedulaCtrl.text.trim();
          final cedValida = esCedulaEcuatorianaValida(ced);

          return AlertDialog(
            title: const Text('Vincular Familiar Adulto (OTP)', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Regla Anti-BOLA (Req. 106): Para representar a un familiar adulto, el titular debe autorizar la delegación mediante un código OTP enviado a su contacto institucional.',
                    style: TextStyle(fontSize: 11, color: Colors.black54),
                  ),
                  const SizedBox(height: 12),
                  if (error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(error!, style: const TextStyle(fontSize: 11, color: Colors.red)),
                    ),
                  if (!otpEnviado) ...[
                    TextField(
                      controller: cedulaCtrl,
                      keyboardType: TextInputType.number,
                      maxLength: 10,
                      decoration: const InputDecoration(
                        labelText: 'Cédula del Titular Adulto',
                        hintText: '1710000025',
                        border: OutlineInputBorder(),
                        counterText: '',
                      ),
                      onChanged: (_) => setModalState(() {}),
                    ),
                    if (ced.length == 10)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          cedValida ? '✓ Cédula válida (Módulo 10)' : '✗ Cédula inválida',
                          style: TextStyle(fontSize: 11, color: cedValida ? Colors.green : Colors.red),
                        ),
                      ),
                  ] else ...[
                    if (debugOtp.isNotEmpty)
                      Container(
                        padding: const EdgeInsets.all(8),
                        margin: const EdgeInsets.only(bottom: 8),
                        decoration: BoxDecoration(color: Colors.blue.shade50, borderRadius: BorderRadius.circular(6)),
                        child: Text('OTP enviado al titular: $debugOtp', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60))),
                      ),
                    TextField(
                      controller: otpCtrl,
                      keyboardType: TextInputType.number,
                      maxLength: 6,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 18, letterSpacing: 6, fontWeight: FontWeight.bold),
                      decoration: const InputDecoration(
                        labelText: 'Código OTP de 6 dígitos',
                        border: OutlineInputBorder(),
                        counterText: '',
                      ),
                      onChanged: (_) => setModalState(() {}),
                    ),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
              if (!otpEnviado)
                ElevatedButton(
                  style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0B3B60)),
                  onPressed: (!cedValida || loading)
                      ? null
                      : () async {
                          setModalState(() {
                            loading = true;
                            error = null;
                          });
                          try {
                            final res = await _api.solicitarDelegacion(ced);
                            setModalState(() {
                              otpEnviado = true;
                              debugOtp = res['debug_otp']?.toString() ?? '';
                              otpCtrl.text = debugOtp;
                            });
                          } on ApiException catch (e) {
                            setModalState(() => error = e.message);
                          } finally {
                            setModalState(() => loading = false);
                          }
                        },
                  child: loading
                      ? const SizedBox(height: 14, width: 14, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                      : const Text('Enviar OTP al Titular', style: TextStyle(color: Colors.white)),
                )
              else
                ElevatedButton(
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green.shade800),
                  onPressed: (otpCtrl.text.trim().length != 6 || loading)
                      ? null
                      : () async {
                          setModalState(() {
                            loading = true;
                            error = null;
                          });
                          try {
                            final delegacion = await _api.confirmarDelegacionOtp(ced, otpCtrl.text.trim());
                            if (!ctx.mounted) return;
                            Navigator.pop(ctx);
                            if (!mounted) return;
                            _showSnackbar('Familiar adulto vinculado exitosamente mediante OTP.', isError: false);
                            await _cargarDelegaciones();
                            setState(() => _beneficiarioCedula = delegacion.beneficiarioCedula);
                            await _cargarMisTurnos();
                          } on ApiException catch (e) {
                            setModalState(() => error = e.message);
                          } finally {
                            setModalState(() => loading = false);
                          }
                        },
                  child: loading
                      ? const SizedBox(height: 14, width: 14, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                      : const Text('Confirmar Delegación', style: TextStyle(color: Colors.white)),
                ),
            ],
          );
        },
      ),
    );
  }

  // ==========================================
  // SESIONES MFA ACTIVAS
  // ==========================================

  void _abrirModalSesiones() async {
    List<UserSessionModel> sesiones = [];
    bool loading = true;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setModalState) {
          if (loading) {
            _api.getActiveSessions().then((list) {
              setModalState(() {
                sesiones = list;
                loading = false;
              });
            }).catchError((_) {
              setModalState(() => loading = false);
            });
          }

          return AlertDialog(
            title: const Row(
              children: [
                Icon(Icons.devices, color: Color(0xFF0B3B60), size: 20),
                SizedBox(width: 8),
                Text('Sesiones MFA Validadas', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ],
            ),
            content: SizedBox(
              width: double.maxFinite,
              child: loading
                  ? const Center(child: Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator()))
                  : sesiones.isEmpty
                      ? const Text('No hay sesiones activas adicionales.')
                      : ListView.separated(
                          shrinkWrap: true,
                          itemCount: sesiones.length,
                          separatorBuilder: (_, _) => const Divider(),
                          itemBuilder: (context, i) {
                            final s = sesiones[i];
                            return ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Row(
                                children: [
                                  Text(s.ip, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
                                  if (s.esActual)
                                    Container(
                                      margin: const EdgeInsets.only(left: 6),
                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(color: Colors.green.shade50, borderRadius: BorderRadius.circular(4)),
                                      child: const Text('Actual', style: TextStyle(fontSize: 10, color: Colors.green, fontWeight: FontWeight.bold)),
                                    ),
                                ],
                              ),
                              subtitle: Text('Actividad: ${s.ultimaActividad.split('T').first}', style: const TextStyle(fontSize: 11)),
                              trailing: IconButton(
                                icon: const Icon(Icons.delete_outline, color: Colors.red, size: 20),
                                onPressed: () async {
                                  try {
                                    await _api.revokeSession(s.id);
                                    final refreshed = await _api.getActiveSessions();
                                    setModalState(() => sesiones = refreshed);
                                  } catch (_) {}
                                },
                              ),
                            );
                          },
                        ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cerrar')),
            ],
          );
        },
      ),
    );
  }

  // ==========================================
  // BUILD PRINCIPAL
  // ==========================================

  @override
  Widget build(BuildContext context) {
    final user = _api.currentUser;

    return Scaffold(
      backgroundColor: const Color(0xFFF3F6F9),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0B3B60),
        elevation: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(user?.nombres ?? 'Afiliado IESS', style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.bold)),
            Text('Cédula: ${user?.cedula} · Rol: AFILIADO', style: const TextStyle(color: Colors.white70, fontSize: 11)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Sesiones MFA',
            icon: const Icon(Icons.security, color: Colors.white),
            onPressed: _abrirModalSesiones,
          ),
          IconButton(
            tooltip: 'Cerrar Sesión',
            icon: const Icon(Icons.logout, color: Colors.white),
            onPressed: () async {
              await _api.logout();
              if (!context.mounted) return;
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (_) => const LoginScreen()),
              );
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                // Barra de Selector de Beneficiario (Anti-BOLA)
                _buildBeneficiarioBar(),

                // Vista de la pestaña actual
                Expanded(
                  child: IndexedStack(
                    index: _currentTabIndex,
                    children: [
                      _buildAgendarTab(),
                      _buildMisTurnosTab(),
                      _buildNotificacionesTab(),
                    ],
                  ),
                ),
              ],
            ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentTabIndex,
        selectedItemColor: const Color(0xFF0B3B60),
        unselectedItemColor: Colors.black54,
        onTap: (index) {
          setState(() => _currentTabIndex = index);
          if (index == 1) _cargarMisTurnos();
          if (index == 2) _cargarNotificaciones();
        },
        items: [
          const BottomNavigationBarItem(icon: Icon(Icons.add_task), label: 'Reservar'),
          BottomNavigationBarItem(
            icon: const Icon(Icons.event_note),
            label: 'Mis Turnos (${_turnos.where((t) => t.estado == "RESERVADO").length})',
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.notifications_none),
            label: 'Avisos (${_notificaciones.length})',
          ),
        ],
      ),
    );
  }

  Widget _buildBeneficiarioBar() {
    final user = _api.currentUser;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: Colors.white,
      child: Row(
        children: [
          const Icon(Icons.family_restroom, size: 20, color: Color(0xFF0B3B60)),
          const SizedBox(width: 8),
          const Text('Atención para:', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
          const SizedBox(width: 8),
          Expanded(
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                isExpanded: true,
                value: _beneficiarioCedula,
                style: const TextStyle(fontSize: 12, color: Colors.black87),
                items: [
                  DropdownMenuItem(
                    value: user?.cedula ?? '',
                    child: Text('Titular: ${user?.nombres ?? ""} (${user?.cedula ?? ""})', overflow: TextOverflow.ellipsis),
                  ),
                  ..._delegaciones.map(
                    (d) => DropdownMenuItem(
                      value: d.beneficiarioCedula,
                      child: Text(
                        '${d.tipoVinculo == "HIJO_MENOR" ? "Hijo Menor" : "Adulto Autorizado"}: ${d.beneficiarioNombre} (${d.beneficiarioCedula})',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                ],
                onChanged: (val) {
                  if (val != null) {
                    setState(() => _beneficiarioCedula = val);
                    _cargarMisTurnos();
                  }
                },
              ),
            ),
          ),
          IconButton(
            tooltip: 'Vincular Familiar Adulto con OTP',
            icon: const Icon(Icons.person_add_alt_1, size: 20, color: Color(0xFF0B3B60)),
            onPressed: _abrirModalVincularFamiliar,
          ),
        ],
      ),
    );
  }

  // ==========================================
  // PESTAÑA 0: AGENDAR / RESERVAR CITA
  // ==========================================

  Widget _buildAgendarTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Card(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Filtros de Búsqueda', style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60))),
                  const SizedBox(height: 10),

                  // Establecimiento
                  DropdownButtonFormField<String>(
                    initialValue: _selectedEstablecimiento.isNotEmpty ? _selectedEstablecimiento : null,
                    decoration: const InputDecoration(labelText: 'Establecimiento Médico', border: OutlineInputBorder(), contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
                    items: _establecimientos.map((e) => DropdownMenuItem(value: e, child: Text(e, style: const TextStyle(fontSize: 12), overflow: TextOverflow.ellipsis))).toList(),
                    onChanged: (val) {
                      if (val != null) {
                        setState(() => _selectedEstablecimiento = val);
                        _consultarSlots();
                      }
                    },
                  ),
                  const SizedBox(height: 10),

                  // Especialidad
                  DropdownButtonFormField<String>(
                    initialValue: _selectedEspecialidad.isNotEmpty ? _selectedEspecialidad : null,
                    decoration: const InputDecoration(labelText: 'Especialidad', border: OutlineInputBorder(), contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
                    items: _especialidades.map((e) => DropdownMenuItem(value: e, child: Text(e, style: const TextStyle(fontSize: 12)))).toList(),
                    onChanged: (val) {
                      if (val != null) {
                        setState(() => _selectedEspecialidad = val);
                        _consultarSlots();
                      }
                    },
                  ),
                  const SizedBox(height: 10),

                  // Fecha
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
                            alignment: Alignment.centerLeft,
                          ),
                          icon: const Icon(Icons.calendar_month, size: 18),
                          label: Text('Fecha: ${_formatDateIso(_selectedFecha)}', style: const TextStyle(fontSize: 12)),
                          onPressed: () async {
                            final picked = await showDatePicker(
                              context: context,
                              initialDate: _selectedFecha,
                              firstDate: DateTime.now(), // Bloqueo de fechas pasadas (Req. 101)
                              lastDate: DateTime.now().add(const Duration(days: 365)),
                            );
                            if (picked != null) {
                              setState(() => _selectedFecha = picked);
                              _consultarSlots();
                            }
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        tooltip: 'Refrescar cupos',
                        icon: const Icon(Icons.refresh, color: Color(0xFF0B3B60)),
                        onPressed: _consultarSlots,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),

          // Grilla de Horarios y Cupos
          Text(
            'Horarios Habilitados (${_grillaSlots.where((s) => s.disponible).length} disponibles):',
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60)),
          ),
          const SizedBox(height: 8),

          if (_loadingSlots)
            const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
          else if (_grillaSlots.isEmpty)
            Card(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              child: const Padding(
                padding: EdgeInsets.all(20),
                child: Center(
                  child: Text('No hay horarios habilitados para esta fecha y especialidad. Intente seleccionando otra fecha futura.', textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: Colors.black54)),
                ),
              ),
            )
          else ...[
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                childAspectRatio: 1.8,
                crossAxisSpacing: 8,
                mainAxisSpacing: 8,
              ),
              itemCount: _grillaSlots.length,
              itemBuilder: (context, i) {
                final slot = _grillaSlots[i];
                final isSelected = _selectedSlot?.hora == slot.hora && _selectedSlot?.medicoCedula == slot.medicoCedula;

                return InkWell(
                  onTap: !slot.disponible
                      ? null
                      : () {
                          setState(() => _selectedSlot = isSelected ? null : slot);
                        },
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                    decoration: BoxDecoration(
                      color: !slot.disponible
                          ? Colors.grey.shade200
                          : (isSelected ? const Color(0xFF0B3B60) : Colors.white),
                      border: Border.all(
                        color: isSelected ? const Color(0xFF0B3B60) : (slot.disponible ? Colors.grey.shade300 : Colors.grey.shade400),
                        width: isSelected ? 2 : 1,
                      ),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          slot.hora,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.bold,
                            color: !slot.disponible ? Colors.grey : (isSelected ? Colors.white : Colors.black87),
                          ),
                        ),
                        Text(
                          slot.disponible ? 'Libre' : 'Ocupado',
                          style: TextStyle(
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            color: !slot.disponible ? Colors.grey.shade600 : (isSelected ? Colors.white70 : Colors.green.shade800),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),

            // Botón de Confirmación
            ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF0B3B60),
                minimumSize: const Size.fromHeight(48),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              icon: _submittingTurno
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                  : const Icon(Icons.check_circle_outline, color: Colors.white),
              label: Text(
                _selectedSlot == null ? 'Seleccione un cupo libre' : 'Confirmar Cita para ${_selectedSlot!.hora}',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
              ),
              onPressed: (_selectedSlot == null || _submittingTurno) ? null : _confirmarReserva,
            ),
          ],
        ],
      ),
    );
  }

  // ==========================================
  // PESTAÑA 1: MIS TURNOS
  // ==========================================

  Widget _buildMisTurnosTab() {
    return RefreshIndicator(
      onRefresh: _cargarMisTurnos,
      child: _loadingTurnos
          ? const Center(child: CircularProgressIndicator())
          : _turnos.isEmpty
              ? ListView(
                  padding: const EdgeInsets.all(24),
                  children: const [
                    SizedBox(height: 60),
                    Icon(Icons.event_busy, size: 50, color: Colors.grey),
                    SizedBox(height: 12),
                    Text('No registra turnos activos para el beneficiario seleccionado.', textAlign: TextAlign.center, style: TextStyle(color: Colors.black54)),
                  ],
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _turnos.length,
                  itemBuilder: (context, i) {
                    final t = _turnos[i];
                    final isReservado = t.estado == 'RESERVADO';

                    return Card(
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      margin: const EdgeInsets.only(bottom: 12),
                      elevation: 1,
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(t.especialidad, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60))),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: t.estado == 'RESERVADO'
                                        ? Colors.blue.shade50
                                        : (t.estado == 'ATENDIDO' ? Colors.green.shade50 : Colors.grey.shade100),
                                    borderRadius: BorderRadius.circular(6),
                                  ),
                                  child: Text(
                                    t.estado,
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.bold,
                                      color: t.estado == 'RESERVADO'
                                          ? Colors.blue.shade800
                                          : (t.estado == 'ATENDIDO' ? Colors.green.shade800 : Colors.black54),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Row(
                              children: [
                                const Icon(Icons.schedule, size: 14, color: Colors.black54),
                                const SizedBox(width: 4),
                                Text('${t.fecha} a las ${t.hora}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text('${t.establecimiento} · Dr(a). ${t.medicoNombre}', style: const TextStyle(fontSize: 11, color: Colors.black54)),
                            const SizedBox(height: 8),

                            // Acciones de Reprogramación / Cancelación
                            if (isReservado) ...[
                              const Divider(height: 12),
                              if (t.puedeModificar24h)
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.end,
                                  children: [
                                    OutlinedButton(
                                      style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6)),
                                      onPressed: () => _reprogramarTurnoDialog(t),
                                      child: const Text('Reprogramar', style: TextStyle(fontSize: 11)),
                                    ),
                                    const SizedBox(width: 8),
                                    OutlinedButton(
                                      style: OutlinedButton.styleFrom(
                                        foregroundColor: Colors.red,
                                        side: const BorderSide(color: Colors.red),
                                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                      ),
                                      onPressed: () => _cancelarTurno(t),
                                      child: const Text('Cancelar', style: TextStyle(fontSize: 11)),
                                    ),
                                  ],
                                )
                              else
                                const Row(
                                  children: [
                                    Icon(Icons.lock_clock, size: 14, color: Colors.amber),
                                    SizedBox(width: 4),
                                    Text('Menor a 24h de anticipación (bloqueado por política)', style: TextStyle(fontSize: 10, color: Colors.amber, fontWeight: FontWeight.w600)),
                                  ],
                                ),
                            ],
                          ],
                        ),
                      ),
                    );
                  },
                ),
    );
  }

  // ==========================================
  // PESTAÑA 2: NOTIFICACIONES SEGURAS
  // ==========================================

  Widget _buildNotificacionesTab() {
    return RefreshIndicator(
      onRefresh: _cargarNotificaciones,
      child: _loadingNotificaciones
          ? const Center(child: CircularProgressIndicator())
          : _notificaciones.isEmpty
              ? ListView(
                  padding: const EdgeInsets.all(24),
                  children: const [
                    SizedBox(height: 60),
                    Icon(Icons.notifications_off_outlined, size: 50, color: Colors.grey),
                    SizedBox(height: 12),
                    Text('Sin notificaciones recientes.', textAlign: TextAlign.center, style: TextStyle(color: Colors.black54)),
                  ],
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _notificaciones.length,
                  itemBuilder: (context, i) {
                    final n = _notificaciones[i];
                    return Card(
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      margin: const EdgeInsets.only(bottom: 10),
                      elevation: 1,
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('[${n.canal}]', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60))),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(color: Colors.blue.shade50, borderRadius: BorderRadius.circular(4)),
                                  child: Text('Estado: ${n.estadoTurno}', style: TextStyle(fontSize: 10, color: Colors.blue.shade800)),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Text(n.mensaje, style: const TextStyle(fontSize: 12)),
                            const SizedBox(height: 6),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('${n.fecha} a las ${n.hora}', style: const TextStyle(fontSize: 10, color: Colors.black54)),
                                Text(n.enlaceRelativo, style: const TextStyle(fontSize: 10, color: Colors.blue, fontStyle: FontStyle.italic)),
                              ],
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
    );
  }
}
