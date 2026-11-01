"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <main id="main" className="container empty-state"><h1>Nie udało się wczytać poradnika.</h1><p>Spróbuj ponownie za chwilę.</p><button className="button" onClick={reset}>Spróbuj ponownie</button></main>; }
