# Implementation Plan - SofizAdmin Financial Monitoring System (G2Bulk + Stellar)

بناء وتطوير نظام الرقابة المالية اللحظي الشامل لمراقبة وتدقيق كل فلس في شركة SofizPay وقسم الألعاب بالاعتماد حصرياً على **G2Bulk API** و **Stellar Wallets**.

> [!IMPORTANT]
معه). الاعتماد فقط على مزود الألعاب الرسمي `G2Bulk` عبر الـ API المباشر.

---

## معادلة الاتزان المالي الأساسية
$$\mathbf{\text{[ رصيد محافظ Stellar + رصيد G2Bulk + الحسابات البنكية ]} + \text{[ إجمالي المصروفات ]} = \text{[ رأس المال الأصلي ]} + \text{[ إجمالي أرباح المبيعات ]}}$$

---

## Proposed Phases & Milestones

### المرحلة 1: تتبع الحسابات والمحافظ ورأس المال (Multi-Wallet & Capital Engine)
- [MODIFY] `monitoring/models.py`: نماذج نظيفة ومبسطة:
  - `CapitalEntry`: تسجيل دفعات رأس المال (تاريخ، مبلغ، عملة، حساب).
  - `StellarWallet`: تتبع عناوين محافظ Stellar (USDT / XLM) ومزامنة رصيدها الحي عبر Horizon API العامة.
  - `SupplierAccount`: تتبع رصيد **G2Bulk** عبر API المباشر `client.get_me()`.
  - `ExpenseRecord`: تسجيل المصروفات وتصنيفها.
  - `BalanceAuditLog`: سجل التدقيق ومطابقة المعادلة وكشف أي فارق.
- [NEW] `monitoring/services/stellar_service.py`: قراءة رصيد Stellar اللحظي من الشبكة (Horizon API).
- [NEW] `monitoring/services/g2bulk_service.py`: قراءة رصيد G2Bulk اللحظي عبر API Key.

### المرحلة 2: محرك المصروفات والتدقيق في الحالات الاستثنائية (Expense Engine)
- تسجيل وتصنيف المصروفات (عمولات شبكة، سيرفرات، بروكسيات، فروقات تحويل، مصاريف تشغيل).
- تسجيل أي استرجاعات مالية (Reversals).

### المرحلة 3: محرك احتساب الأرباح الآلي (Automated Profit Engine)
- احتساب أرباح طلبات G2Bulk (سعر البيع للزبون - سعر التكلفة من G2Bulk).
- تجميع إجمالي الأرباح اللحظية والتراكمية.

### المرحلة 4: ميزان الاتزان اللحظي وكاشف الخلل (Golden Balance Engine)
- [NEW] `monitoring/services/balance_engine.py`: اختبار المعادلة الدورية `(Total Balances + Total Expenses == Total Capital + Total Profits)`.
- تنبيه فوري وتسجيل أي خلل مالي لا يساوي الصفر.

### المرحلة 5: لوحة التحكم والتقارير التفاعلية (Dashboard)
- [MODIFY] `monitoring/templates/monitoring/index.html`: واجهة مظلمة فاخرة تعرض الأرصدة الحية، رأس المال، الأرباح، والمصروفات مع ميزان الاتزان اللحظي.

---

## Verification Plan
### Automated Tests
- تشغيل اختبارات التحقق المالي لمزامنة G2Bulk و Stellar:
  `python manage.py test monitoring`
- تشغيل النظام عبر Docker والتأكد من استقرار الخوادم:
  `docker compose up -d`
