#version 330 core

in vec2 out_pos;
out vec4 f_color;
uniform float time;

void main()
{
    vec2 uv = gl_FragCoord.xy / vec2(1600.0 / 900.0);
    vec2 ndc = uv * 2.0 - 1.0;
    ndc.y *= -1.0;
    
    float wave = sin(ndc.x * 10.0 + time * 5.0);
    f_color = vec4(abs(out_pos.y) * 5, 1.0 - abs(out_pos.y) * 5, wave, 1.0);
}