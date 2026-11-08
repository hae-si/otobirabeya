export function setupFullscreen({target,button,onResize=()=>{}}){
 let fallback=false;
 const active=()=>fallback||document.fullscreenElement===target;
 function sync(){const expanded=active();target.classList.toggle('expanded-browser',expanded);document.body.classList.toggle('browser-expanded',expanded);button.textContent=expanded?'退出全屏':'全屏浏览';button.setAttribute('aria-pressed',String(expanded));requestAnimationFrame(onResize);}
 async function exit(){fallback=false;if(document.fullscreenElement===target)await document.exitFullscreen();sync();}
 button.onclick=async()=>{if(active()){await exit();return;}try{if(!target.requestFullscreen)throw Error('unsupported');await target.requestFullscreen();}catch{fallback=true;}sync();};
 document.addEventListener('fullscreenchange',sync);
 document.addEventListener('keydown',event=>{if(active()&&(event.key==='Escape'||event.key==='Esc'||event.code==='Escape')){event.preventDefault();exit();}});
 sync();
}
