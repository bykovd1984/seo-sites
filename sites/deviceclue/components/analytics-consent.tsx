export function AnalyticsConsent() {
  return <aside className="consent-banner" aria-label="Privacy choices" data-consent-banner hidden>
      <div><p className="eyebrow">YOUR PRIVACY, YOUR CALL</p><h2>A little insight. With your permission.</h2><p>We use optional Google Analytics to understand which guides are useful. You can decline and use every page. <a href="/privacy">How your data is used</a></p></div>
      <div className="consent-actions"><button type="button" data-consent="rejected">Essential only</button><button type="button" data-consent="accepted">Allow analytics</button></div>
    </aside>;
}
