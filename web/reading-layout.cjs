function orientForReading(nodes){
 const mean=items=>items.reduce((a,n)=>({x:a.x+n.x/items.length,y:a.y+n.y/items.length}),{x:0,y:0});
 const center=mean(nodes),chinese=nodes.filter(n=>n.language_class==='inferred_chinese'),target=chinese.length?mean(chinese):center;
 const dx=target.x-center.x,dy=target.y-center.y;
 const angle=Math.hypot(dx,dy)>1e-9?Math.PI/2-Math.atan2(dy,dx):0,c=Math.cos(angle),s=Math.sin(angle);
 const positions=Object.fromEntries(nodes.map(n=>{const x=n.x-center.x,y=n.y-center.y;return [n.id,{x:c*x-s*y,y:s*x+c*y}];}));
 const values=Object.values(positions),xs=values.map(n=>n.x),ys=values.map(n=>n.y);
 return {positions,bbox:{x:values.length?[Math.min(...xs),Math.max(...xs)]:[-1,1],y:values.length?[Math.min(...ys),Math.max(...ys)]:[-1,1]}};
}
module.exports={orientForReading};
