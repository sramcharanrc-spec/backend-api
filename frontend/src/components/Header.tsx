import React, { useEffect, useState } from "react";
import {
  Bell,
  UserCircle2,
  Moon,
  Sun,
  Sparkles
} from "lucide-react";
import { useNavigate } from "react-router-dom";

const Header: React.FC = () => {

const [darkMode,setDarkMode]=useState(
localStorage.getItem("theme")==="dark"
);

const [isLoggingOut,setIsLoggingOut]=
useState(false);

const navigate=useNavigate();

useEffect(()=>{

if(darkMode){

document.body.classList.add("dark");

localStorage.setItem(
"theme",
"dark"
);

}else{

document.body.classList.remove(
"dark"
);

localStorage.setItem(
"theme",
"light"
);

}

},[darkMode]);

const handleLogout=()=>{

if(isLoggingOut) return;

setIsLoggingOut(true);

setTimeout(()=>{

localStorage.removeItem(
"isLoggedIn"
);

localStorage.removeItem(
"user"
);

navigate(
"/login",
{
replace:true
}
);

},850);

};

return(

<header
className="
h-[72px]
relative
sticky
top-0
z-50
flex
items-center
justify-between
px-8
overflow-hidden
backdrop-blur-xl
bg-[#060B1F]/95
border-b
border-cyan-500/10
shadow-[0_8px_30px_rgba(0,0,0,.45)]
"
>

{/* Background */}

<div
className="
absolute
inset-0
pointer-events-none
overflow-hidden
"
>

{/* soft animated glow */}

<div
className="
absolute
left-[20%]
top-[-150px]
w-[300px]
h-[300px]
rounded-full
bg-cyan-500/10
blur-[120px]
animate-[floatX_8s_ease-in-out_infinite]
"
/>

<div
className="
absolute
right-[20%]
top-[-150px]
w-[300px]
h-[300px]
rounded-full
bg-purple-500/10
blur-[120px]
animate-[floatY_10s_ease-in-out_infinite]
"
/>

{/* thin moving line */}

<div
className="
absolute
top-0
left-[-50%]
w-[200%]
h-[1px]
bg-gradient-to-r
from-transparent
via-cyan-400
to-transparent
opacity-50
animate-[moveLine_7s_linear_infinite]
"
/>

</div>

{/* Left section */}

<div
className="
relative
z-10
flex
items-center
gap-4
"
>

<div
className="
w-11
h-11
rounded-2xl
bg-gradient-to-br
from-cyan-500
via-blue-500
to-indigo-600
flex
items-center
justify-center
shadow-[0_0_25px_rgba(34,211,238,.4)]
hover:scale-105
transition-all
"
>

<Sparkles
size={18}
className="
text-white
"
/>

</div>

<div>

<h1
className="
text-[24px]
font-bold
leading-none
"
>

<span className="
ml-2
bg-gradient-to-r
from-cyan-400
to-purple-500
bg-clip-text
text-transparent
"
>

AgenticAI

</span>

<span
className="
ml-2
bg-gradient-to-r
from-cyan-400
to-purple-500
bg-clip-text
text-transparent
"
>

Health

</span>

</h1>

<div
className="
text-[9px]
tracking-[3px]
uppercase
text-cyan-500/100
mt-1
"
>

AI Revenue Command Center

</div>

</div>

</div>


{/* Right */}

<div
className="
relative
z-10
flex
items-center
gap-3
"
>

{/* Theme */}

<button
onClick={()=>
setDarkMode(
!darkMode
)
}
className="
w-10
h-10
rounded-xl
bg-[#111B38]/70
border
border-white/10
hover:border-cyan-400
hover:bg-cyan-500/10
transition-all
duration-300
flex
items-center
justify-center
"
>

{
darkMode
?

<Sun
size={18}
className="
text-yellow-300
"
/>

:

<Moon
size={18}
className="
text-cyan-300
"
/>

}

</button>


{/* Notification */}

<button
className="
relative
w-10
h-10
rounded-xl
bg-[#111B38]/70
border
border-white/10
hover:border-purple-400
hover:bg-purple-500/10
transition-all
duration-300
flex
items-center
justify-center
"
>

<Bell
size={18}
className="
text-white
"
/>

<span
className="
absolute
top-2
right-2
w-2
h-2
rounded-full
bg-red-500
animate-pulse
"
/>

</button>


{/* User */}

<div
className="
flex
items-center
gap-3
px-4
h-11
rounded-xl
bg-[#111B38]/70
border
border-white/10
hover:border-cyan-400
transition-all
"
>

<UserCircle2
size={22}
className="
text-cyan-400
"
/>

<div>

<div
className="
text-sm
font-semibold
text-white
"
>

{
JSON.parse(
localStorage.getItem(
"user"
)||"{}"
).email
||
"test@clinic.com"
}

</div>

<div
className="
text-[10px]
text-gray-400
"
>

AI Operator

</div>

</div>

</div>


{/* Logout */}

<button
  onClick={handleLogout}
  disabled={isLoggingOut}
  className={[
    `
    h-11
    px-5
    rounded-xl
    bg-gradient-to-r
    from-indigo-600
    to-purple-600
    text-white
    font-medium
    flex
    items-center
    justify-center
    gap-2
    hover:shadow-[0_0_20px_rgba(99,102,241,.6)]
    hover:scale-105
    transition-all
    duration-300
    relative
    overflow-hidden
    `,
    darkMode
      ? "logout-button--light"
      : "logout-button--dark",
    isLoggingOut
      ? "is-logging-out"
      : "",
  ].join(" ")}
>

  {/* animated background glow */}

  <span
    className="
    absolute
    inset-0
    bg-gradient-to-r
    from-cyan-500/20
    to-purple-500/20
    opacity-0
    hover:opacity-100
    transition-opacity
    duration-500
    "
  />

  <span
    className="
    logout-button__label
    relative
    z-10
    "
  >
    Logout
  </span>

  <span
    className="
    logout-button__icon
    relative
    z-10
    "
  >
    <span className="logout-button__person" />
    <span className="logout-button__door" />
  </span>

</button>

</div>

</header>
);

};

export default Header;