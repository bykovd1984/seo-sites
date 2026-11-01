export const metadata={title:'Privacy',description:'How the DeviceClue reading and search features handle information.',alternates:{canonical:'/privacy'}};
export default function Privacy(){return <main id="main" className="container simple-page">
  <nav className="breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span><span>Privacy</span></nav>
  <p className="eyebrow">PRIVACY</p><h1 className="page-title">Your choice comes first.</h1>
  <div className="prose">
    <p>DeviceClue uses optional Google Analytics to understand visits and which guides people use. The Google tag loads only after you choose “Allow analytics”. Choosing “Essential only” lets you use every page without loading that tag.</p>
    <h2>Your privacy choice</h2>
    <p>We save your choice in your browser’s local storage so you do not need to answer on every visit. You can change it at any time using “Privacy settings” in the footer. If you withdraw consent, the application disables Analytics, removes its first-party Analytics cookies, and reloads the page without the Google tag.</p>
    <h2>Optional Analytics</h2>
    <p>After consent, Google Analytics receives information such as page paths, browser and device information, and usage events. It can use first-party Analytics cookies to distinguish visits. This site configures those cookies with a 180-day lifetime, which can be renewed by subsequent visits. Google Signals and ad personalization are disabled, and advertising consent remains denied.</p>
    <p>We remove query strings and fragments from page addresses and referring-page URLs before sending them to Analytics. Automatic site-search, form-interaction, video and browser-history pageview measurement are disabled. See <a href="https://policies.google.com/privacy">Google’s privacy policy</a> for how Google handles information.</p>
    <h2>Search</h2>
    <p>Search terms are sent to this site in the URL to retrieve matching guides. The application does not store search histories. Your browser history may contain the visited URL, so do not put personal or sensitive information into the search box.</p>
    <h2>Hosting</h2>
    <p>Pages are served from a virtual private server. Your IP address and ordinary connection information are processed to deliver the requested pages. For reliability, the application sends operational logs to our server’s Elasticsearch system: published page paths, request methods, response status, duration, and general startup or error events. These logs use a 30-day retention policy, with removal following the server’s lifecycle schedule. They do not include IP addresses, request headers, cookies, search text, query strings or arbitrary unrecognized paths. They operate independently of optional Analytics. Server-level security or diagnostic logging may still process connection information. There are no accounts, comment forms, newsletter sign-ups or user database.</p>
    <h2>External sources</h2>
    <p>Manufacturer and official-source links take you to other websites, which have their own privacy practices. Their content is not embedded here. The site does not load advertising, third-party fonts or embedded video.</p>
  </div>
</main>;}
