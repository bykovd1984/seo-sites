export function AnalyticsConsent() {
return <aside className="consent-banner" aria-label="Ustawienia prywatności" data-consent-banner hidden>
     <div><h2>Twój wybór prywatności</h2><p>Za Twoją zgodą używamy Google Analytics, aby poznać ruch i korzystanie z poradników. Możesz odmówić i nadal korzystać z całej strony. <a href="/prywatnosc">Szczegóły prywatności</a></p></div>
     <div className="consent-actions"><button type="button" data-consent="rejected">Tylko niezbędne</button><button type="button" data-consent="accepted">Zgadzam się na analitykę</button></div>
   </aside>;
}
