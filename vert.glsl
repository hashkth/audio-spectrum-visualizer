#version 330 core

in vec2 in_pos;
out vec2 out_pos;

void main()
{
    gl_Position = vec4(in_pos, 0.0, 1.0);
    out_pos = in_pos;
}