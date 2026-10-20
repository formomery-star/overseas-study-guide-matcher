const fs=require('fs'),path=require('path'),os=require('os'),{pathToFileURL}=require('url');
let playwright;try{playwright=require('playwright')}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'))}
(async()=>{const input=path.resolve(process.argv[2]);const launch={headless:true};if(process.env.GUIDE_BROWSER)launch.executablePath=process.env.GUIDE_BROWSER;else if(process.platform==='win32')launch.executablePath='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
 const browser=await playwright.chromium.launch(launch);
 try{const page=await browser.newPage({viewport:{width:1200,height:850}});await page.goto(pathToFileURL(input).href);await page.evaluate(()=>document.fonts.ready);
 const qa=await page.evaluate(()=>[...document.querySelectorAll('.page')].map((s,i)=>{const r=s.getBoundingClientRect(),f=s.querySelector('footer').getBoundingClientRect(),m=s.querySelector('main');const bad=[...m.querySelectorAll('*')].filter(e=>!e.closest('svg')).filter(e=>{const b=e.getBoundingClientRect();return b.bottom>f.top-5||b.right>r.right-25||b.left<r.left+20});return {page:i+1,title:s.querySelector('h1').textContent,bottom:Math.round(m.getBoundingClientRect().bottom-r.top),footer:Math.round(f.top-r.top),overflow:bad.map(e=>e.textContent.slice(0,45))};}));
 fs.writeFileSync(path.join(path.dirname(input),'版面检查.json'),JSON.stringify(qa,null,2));
 if(qa.some(x=>x.overflow.length))throw new Error('版面溢出，未输出PDF：'+JSON.stringify(qa.filter(x=>x.overflow.length)));
 if(!process.argv.includes('--check-only'))await page.pdf({path:input.replace(/\.html$/,'.pdf'),printBackground:true,preferCSSPageSize:true});
 console.log('PDF '+qa.length+' pages; layout OK');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
