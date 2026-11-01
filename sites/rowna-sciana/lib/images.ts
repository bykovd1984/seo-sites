import manifest from "../public/images/optimized-manifest.json";
const images = manifest as Record<string,{src:string;small:string;width:number;height:number}>;
export function optimizedImage(source:string) {
 return images[source] || Object.values(images).find(image=>image.src===source);
}
export function imageAttributes(source:string,kind:"hero"|"card"|"article") {
 const image=optimizedImage(source);
 return image ? {src:image.src,srcSet:`${image.small} 640w, ${image.src} ${image.width}w`,
 sizes:kind==="card"?"(max-width: 760px) calc(100vw - 40px), 400px":kind==="hero"?"(max-width: 760px) calc(100vw - 40px), 600px":"(max-width: 900px) calc(100vw - 40px), 780px"} : {src:source};
}
