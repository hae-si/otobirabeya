export function dataUrl(path){
 const version=document.documentElement.dataset.dataVersion;
 return version?path+(path.includes('?')?'&':'?')+'v='+encodeURIComponent(version):path;
}
