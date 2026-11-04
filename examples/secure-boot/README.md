# Secure boot, in a project that is not ours

A plain CMake firmware project with its own startup code, linker script and test output. It uses nothing from VirtuLab. All VirtuLab needs is [`virtulab.yml`](virtulab.yml): the build command, the images it produces, and which function to attack.

```sh
virtulab run                                  # hardened check: no bypass
```

To see what the sweep finds in a plain digest check, turn the hardening off:

```sh
rm -rf build
sed -i.bak 's/"cmake -S . -B build\/vl/"cmake -S . -B build\/vl -DBOOT_HARDENED=OFF/' virtulab.yml
virtulab run                                  # unit tests pass, a tampered image can boot
```

The digest here is a stand-in, not cryptography. A real bootloader verifies a signature, and the same sweep applies to the comparison around it.

What a project needs to do:

- Exit through Arm semihosting.
- Print results in Unity's format.
- In a fault probe, print `auth bypass` when the property breaks.
