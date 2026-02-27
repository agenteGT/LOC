# Documentación de Reglas de Decisión: LOC - KIE/Kogito

## 1. Descripción General
Este documento detalla la lógica de negocio, reglas de validación y cálculos matemáticos para el producto de crédito **LOC (Line of Credit)** implementado sobre la plataforma Red Hat KIE / Kogito.

El flujo cubre desde la recepción de la solicitud (`LoanRequest`), limpieza de datos, validación de reglas de negocio (Hard Gates), hasta el cálculo de capacidad de pago y estructuración de la deuda final.

---

## 2. Modelo de Datos (Inputs y Outputs)

### 2.1 Inputs (Entradas)
Datos requeridos para iniciar el proceso de evaluación. Objeto principal: `LoanRequest`.

| Variable | Campo KIE | Tipo | Descripción | Restricciones | Ejemplo |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **imd** | `loanRequest.imd` | Double | Ingreso Mensual Disponible del cliente | `>= 0` | `1000` |
| **term** | `loanRequest.term` | Integer | Plazo del crédito en meses | `∈ {2, 3, 4, 5}` | `2` |
| **fee** | `loanRequest.fee` | Double | Tasa de comisión (decimal) | `>= 0` | `0.20` |
| **roundUnit** | `loanRequest.roundUnit` | Integer | Unidad de redondeo hacia abajo | `> 0` | `50` |
| **maxCap** | `loanRequest.maxCap` | Double | Techo máximo del monto aprobado | `> 0` | `3500` |
| **productType** | `loanRequest.productType` | String | Tipo de producto | Debe ser "LOC" | `"LOC"` |

### 2.2 Outputs (Salidas)
Resultados calculados por el motor de reglas.

| Variable | Campo KIE | Tipo | Descripción |
| :--- | :--- | :--- | :--- |
| **rawAmount** | `loanRequest.rawAmount` | Double | Monto bruto calculado antes de redondeo y cap. |
| **maxAmount** | `loanRequest.maxAmount` | Double | Monto máximo aprobado final (redondeado y capeado). |
| **interest** | `loanRequest.interest` | Double | Monto total de intereses generados. |
| **totalDebt** | `loanRequest.totalDebt` | Double | Deuda total (Capital + Intereses). |
| **status** | `loanRequest.status` | String | Estado final: `APPROVED` o `REJECTED`. |
| **reason** | `loanRequest.reason` | String | Razón del rechazo (si aplica). |

---

## 3. Flujo de Ejecución (Salience)

El motor ejecuta las reglas basándose en la prioridad (`salience`). Un valor más alto indica mayor prioridad.

1.  **Limpieza (Salience 90-100):** Normalización de nulos y negativos.
2.  **Validación (Salience 80):** Reglas de rechazo (Hard Gates).
3.  **Cálculo (Salience 20-50):** Fórmulas matemáticas (solo si no fue rechazado).
4.  **Output (Salience 10):** Generación de respuesta final.

---

## 4. Detalle de Reglas de Negocio

### Paso 2: Limpieza de Datos (Data Cleansing)
*Objetivo: Asegurar que no existan valores nulos o negativos antes de procesar.*

| Regla | Condición (WHEN) | Acción (THEN) | Salience |
| :--- | :--- | :--- | :--- |
| **Clean-Null-*** | Variable es `null` | Asignar `0` | 100 |
| **Clean-Neg-*** | Variable `< 0` | Asignar `0` | 90 |

**Ejemplo DRL (Limpieza):**
```drl
rule "Clean-Null-IMD"
salience 100
when
  $r : LoanRequest(imd == null)
then
  $r.setImd(0.0);
  update($r);
end
```

### Paso 3: Validación (Validation Gate)
*Objetivo: Rechazar solicitudes que no cumplen con los criterios mínimos.*

| Regla | Condición | Resultado | Razón |
| :--- | :--- | :--- | :--- |
| **Validate-Zero-IMD** | `imd == 0` | `REJECTED` | "IMD es 0" |
| **Validate-Invalid-Term** | `term ∉ [2,3,4,5]` | `REJECTED` | "Plazo inválido" |
| **Validate-Zero-Fee** | `fee == 0` | `REJECTED` | "Fee es 0" |
| **Validate-Product-Type** | `productType != "LOC"` | `REJECTED` | "Producto no LOC" |

**Ejemplo DRL (Validación):**
```drl
rule "Validate-Invalid-Term"
salience 80
when
  $r : LoanRequest(term not memberOf [2,3,4,5])
then
  $r.setStatus("REJECTED");
  $r.setMaxAmount(0.0);
  $r.setReason("Plazo inválido");
end
```

### Paso 4: Lógica de Cálculo (Computation Rules)
*Se ejecuta solo si `status != REJECTED`.*

#### Fórmulas Matemáticas
1.  **Monto Bruto ($$C1$$):**
    $$C1 = \frac{IMD \times term}{1 + fee}$$

2.  **Monto Máximo (Redondeo y Cap):**
    $$maxAmount = \min\left( \left\lfloor \frac{C1}{roundUnit} \right\rfloor \times roundUnit, \quad maxCap \right)$$
    *(Donde `roundUnit` = 50 y `maxCap` = 3500)*

3.  **Intereses:**
    $$intereses = maxAmount \times fee$$

4.  **Deuda Total:**
    $$deuda = maxAmount \times (1 + fee)$$

#### Implementación DRL de Cálculos

**4.1 Calcular Monto Bruto (Salience 50)**
```drl
rule "LOC-Calc-RawAmount"
salience 50
when
  $r : LoanRequest(productType == "LOC", status != "REJECTED", imd > 0)
then
  double raw = ($r.getImd() * $r.getTerm()) / (1 + $r.getFee());
  $r.setRawAmount(raw);
  update($r);
end
```

**4.2 Redondeo (Salience 40)**
```drl
rule "LOC-Calc-MaxAmount"
salience 40
when
  $r : LoanRequest(productType == "LOC", rawAmount > 0)
then
  int unit = $r.getRoundUnit();
  double max = Math.floor($r.getRawAmount() / unit) * unit;
  $r.setMaxAmount(max);
  update($r);
end
```

**4.3 Aplicar Techo/Cap (Salience 35)**
```drl
rule "LOC-Calc-ApplyCap"
salience 35
when
  $r : LoanRequest(productType == "LOC", maxAmount > maxCap)
then
  $r.setMaxAmount($r.getMaxCap());
  update($r);
end
```

**4.4 Intereses y Deuda Final (Salience 30-20)**
```drl
rule "LOC-Calc-TotalDebt"
salience 20
when
  $r : LoanRequest(productType == "LOC", maxAmount > 0)
then
  double debt = $r.getMaxAmount() * (1 + $r.getFee());
  $r.setTotalDebt(debt);
  $r.setStatus("APPROVED");
  update($r);
end
```

---

## 5. Casos de Prueba de Referencia

Escenarios basados en `IMD = 1000`, `roundUnit = 50`, `maxCap = 3500`.

| Plazo (meses) | Fee | Cálculo Bruto (C1) | maxAmount (Pre-Cap) | maxAmount (Final) | Intereses | Deuda Total |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2** | 20% | 1,666.67 | 1,650 | **1,650** | 330.0 | 1,980.0 |
| **3** | 5% | 2,857.14 | 2,850 | **2,850** | 142.5 | 2,992.5 |
| **4** | 5% | 3,809.52 | 3,800 | **3,500** ⚠️ | 175.0 | 3,675.0 |
| **5** | 5% | 4,761.90 | 4,750 | **3,500** ⚠️ | 175.0 | 3,675.0 |

---

## 6. Implementación Técnica (Java)

Estructura del Data Object para KIE Sandbox / Kogito.

```java
public class LoanRequest implements java.io.Serializable {

    // ─── INPUTS ───
    private String productType;    // "LOC"
    private Double imd;            // Ingreso Mensual Disponible
    private Integer term;          // Plazo en meses (2,3,4,5)
    private Double fee;            // Tasa de fee (decimal)
    private Integer roundUnit;     // Unidad de redondeo (50)
    private Double maxCap;         // Techo máximo del monto (3500)

    // ─── OUTPUTS ───
    private Double rawAmount;      // Calculado
    private Double maxAmount;      // Calculado (Final)
    private Double interest;       // Calculado
    private Double totalDebt;      // Calculado
    private String status;         // APPROVED / REJECTED
    private String reason;         // Motivo rechazo

    public LoanRequest() {}

    // Getters y Setters estándar...
}
```

### Notas de Integración
1.  **Endpoint Esperado:** `POST /api/loc-calculation`
2.  **Payload JSON:**
    ```json
    {
      "productType": "LOC",
      "imd": 1000,
      "term": 2,
      "fee": 0.20,
      "roundUnit": 50,
      "maxCap": 3500
    }
    ```
3.  **Configuración:** El `fee` no se busca en tabla interna, se recibe como input. `maxCap` y `roundUnit` son parametrizables vía input.