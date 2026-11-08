const input=document.querySelector('#guide-search');
if(input instanceof HTMLInputElement){
  const cards=[...document.querySelectorAll('[data-guide]')];
  const counter=document.querySelector('#result-count');
  const empty=document.querySelector('#no-results');
  const params=new URLSearchParams(location.search);
  input.value=(params.get('q')||'').slice(0,120);
  const filter=()=>{
    const words=input.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let count=0;
    for(const card of cards){
      const show=words.every(word=>card.dataset.search.includes(word));
      card.hidden=!show;if(show)count++;
    }
    if(counter)counter.textContent=words.length?`${count} matching guide${count===1?'':'s'}`:`${count} guides`;
    if(empty)empty.hidden=count!==0;
  };
  input.addEventListener('input',filter);
  input.form?.addEventListener('submit',event=>{
    event.preventDefault();
    const query=input.value.trim();
    history.replaceState(null,'',query?`/search/?q=${encodeURIComponent(query)}`:'/search/');
    filter();
  });
  filter();
}
