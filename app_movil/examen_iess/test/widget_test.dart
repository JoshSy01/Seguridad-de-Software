import 'package:flutter_test/flutter_test.dart';
import 'package:examen_iess/main.dart';
import 'package:examen_iess/services/security_utils.dart';

void main() {
  testWidgets('Prueba de humo y renderizado inicial de IESS Turnos Móvil', (WidgetTester tester) async {
    await tester.pumpWidget(const IessTurnosApp());

    // Verificar que la barra superior muestra el título de la app
    expect(find.text('IESS · Turnos Móvil'), findsOneWidget);

    // Verificar que se renderiza el botón para continuar y para activar cuenta
    expect(find.text('Portal Afiliados IESS'), findsOneWidget);
    expect(find.text('Continuar'), findsOneWidget);
    expect(find.text('Activar Cuenta de Afiliado (Registro)'), findsOneWidget);
  });

  test('Validación de Cédula Ecuatoriana (Módulo 10)', () {
    // Válidas
    expect(esCedulaEcuatorianaValida('1710000017'), isTrue);
    expect(esCedulaEcuatorianaValida('1710000025'), isTrue);
    expect(esCedulaEcuatorianaValida('1710000058'), isTrue);

    // Inválidas
    expect(esCedulaEcuatorianaValida('1710000011'), isFalse); // Verificador erróneo
    expect(esCedulaEcuatorianaValida('9910000015'), isFalse); // Provincia inválida
    expect(esCedulaEcuatorianaValida('1760000019'), isFalse); // Tercer dígito >= 6
    expect(esCedulaEcuatorianaValida('0000000000'), isFalse); // Repetidos
    expect(esCedulaEcuatorianaValida('123'), isFalse);        // Longitud menor
  });
}
